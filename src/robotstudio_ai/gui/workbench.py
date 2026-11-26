"""Phase 2 scene workbench built on the validated Phase 1 robot viewer."""

import logging
import sys
import warnings
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from scipy.spatial.transform import Rotation

from robotstudio_ai import __version__
from robotstudio_ai.core.project_io import (
    CameraState,
    SceneProject,
    import_mesh,
    load_project,
    save_project,
)
from robotstudio_ai.core.scene import (
    BoxShape,
    CylinderShape,
    FrameShape,
    MeshShape,
    RobotSource,
    SceneDocument,
    SceneManager,
    SceneObject,
    SceneRobot,
    SphereShape,
)
from robotstudio_ai.core.schema import JointState, Pose
from robotstudio_ai.core.transforms import matrix_pose
from robotstudio_ai.gui.main_window import MainWindow
from robotstudio_ai.gui.object_editor import KINDS, ObjectEditor
from robotstudio_ai.gui.scene_view import SceneView, object_surface
from robotstudio_ai.gui.viewport import prepare_surfaces
from robotstudio_ai.scene_profiles import load_robot_source, model_fingerprint, source_from_settings

LOGGER = logging.getLogger(__name__)


class JobSignals(QObject):
    ready = Signal(object)
    failed = Signal(str)
    finished = Signal()


class ResourceJob(QRunnable):
    def __init__(self, task: Callable):
        super().__init__()
        self.task = task
        self.signals = JobSignals()

    def run(self):
        try:
            self.signals.ready.emit(self.task())
        except Exception as error:
            LOGGER.exception("Scene resource operation failed")
            self.signals.failed.emit(str(error))
        finally:
            self.signals.finished.emit()


class SceneWorkbench(MainWindow):
    """SceneManager is authoritative; UI and rendering consume the same document."""

    def __init__(self, *args, cache_dir: Path | None = None, **kwargs):
        self._suspend_scene_sync = True
        self._syncing_to_scene = False
        self._robot_edit_key = None
        self.selected_id: str | None = None
        self.selected_robot = False
        self.project_path: Path | None = None
        self._extra_jobs = []
        self._tree_signature = None
        super().__init__(*args, **kwargs)
        root = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[3]
        )
        self.cache_dir = cache_dir or root / ".cache" / "scene_assets"
        self.current_source = source_from_settings(self.settings, self.model)
        self.scene = SceneManager(SceneDocument(robot=self._capture_robot()))
        self.scene_view = SceneView(self.viewport)
        self.scene_view.picked.connect(self.select_item)
        self.scene_view.transformed.connect(self._object_transformed)
        self.scene_view.drag_finished.connect(self._end_gesture)
        self._build_scene_tools()
        self._build_project_menu()
        self.scene.subscribe(self._scene_changed)
        self._suspend_scene_sync = False
        self.tree.itemChanged.connect(self._tree_visibility)
        self.axes_toggle.toggled.connect(lambda _: self._sync_view())
        self._scene_changed(None)

    def _capture_robot(self) -> SceneRobot:
        previous = self.scene.document.robot if hasattr(self, "scene") else None
        values = dict(
            source=self.current_source,
            joints=JointState(
                names=tuple(j.name for j in self.model.active_joints), positions=tuple(self.q)
            ),
            base=self.base,
            tool_offset=self.tool_offset,
            tool_link=self.tool_link,
        )
        if previous:
            values.update(id=previous.id, visible=previous.visible)
        return SceneRobot(**values)

    def _build_scene_tools(self):
        self.editor = ObjectEditor()
        self.editor.apply_requested.connect(self.apply_properties)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        properties_panel = QWidget()
        properties_layout = QVBoxLayout(properties_panel)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.addWidget(scroll, 1)
        self.editor.layout().removeWidget(self.editor.apply_button)
        properties_layout.addWidget(self.editor.apply_button)
        self.tabs.addTab(properties_panel, "객체 속성")
        self.tabs.currentChanged.connect(lambda index: self.tcp_group.setVisible(index != 2))
        self.tree.setMinimumWidth(210)
        self.tree.setHeaderLabel("로봇 / 작업환경")
        self.environment_buttons = []
        row = QHBoxLayout()
        for text, shape in (
            ("+ 상자", "box"),
            ("+ 원통", "cylinder"),
            ("+ 구", "sphere"),
            ("+ 좌표계", "frame"),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, kind=shape: self.create_primitive(kind))
            row.addWidget(button)
            self.environment_buttons.append(button)
        for text, callback in (
            ("STL/OBJ 가져오기", self.import_dialog),
            ("복제", self.duplicate_selected),
            ("삭제", self.delete_selected),
            ("예제 환경", self.load_demo),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.environment_buttons.append(button)
        from PySide6.QtWidgets import QCheckBox

        self.manipulate = QCheckBox("마우스 이동·회전")
        self.manipulate.setChecked(True)
        self.manipulate.toggled.connect(lambda _: self._sync_view())
        row.addWidget(self.manipulate)
        row.addStretch()
        self.centralWidget().layout().insertLayout(2, row)
        for button in self.centralWidget().findChildren(QPushButton):
            if button.text() == "화면 맞춤":
                button.clicked.disconnect()
                button.clicked.connect(self.scene_view.fit_all)

    def _build_project_menu(self):
        menus = self.menuBar().actions()
        file_menu = menus[0].menu()
        first = file_menu.actions()[0]
        for text, shortcut, callback in (
            ("새 작업환경", "Ctrl+N", self.new_scene_dialog),
            ("작업환경 열기…", "Ctrl+O", self.open_project_dialog),
            ("작업환경 저장", "Ctrl+S", self.save_dialog),
            ("다른 이름으로 저장…", "Ctrl+Shift+S", self.save_as_dialog),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            file_menu.insertAction(first, action)
        first.setShortcut("Ctrl+Shift+O")
        edit = self.menuBar().addMenu("편집")
        self.undo_action = QAction("되돌리기", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.scene.undo)
        edit.addAction(self.undo_action)
        self.redo_action = QAction("다시 실행", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.scene.redo)
        edit.addAction(self.redo_action)
        edit.addAction("객체 복제", self.duplicate_selected)
        edit.addAction("객체 삭제", self.delete_selected)
        view = menus[1].menu()
        view.addAction("전체 작업환경 맞춤", self.scene_view.fit_all)
        escape = QAction(self)
        escape.setShortcut("Escape")
        escape.triggered.connect(lambda: self.select_item(""))
        self.addAction(escape)

    def apply_model(self, *args, **kwargs):
        previous = self._suspend_scene_sync
        self._suspend_scene_sync = True
        if hasattr(self, "scene_view"):
            self.scene_view.model_was_cleared()
        try:
            super().apply_model(*args, **kwargs)
        finally:
            self._suspend_scene_sync = previous
        for control in self.controls:
            control.slider.sliderReleased.connect(self._end_gesture)
            control.spin.editingFinished.connect(self._end_gesture)

    def refresh_pose(self):
        super().refresh_pose()
        if hasattr(self, "scene") and not self._suspend_scene_sync:
            self._syncing_to_scene = True
            try:
                self.scene.update_robot(self._capture_robot(), key=self._robot_edit_key)
            finally:
                self._syncing_to_scene = False
            self._sync_view()

    def set_joint(self, index, value):
        self._robot_edit_key = f"joint:{index}"
        try:
            super().set_joint(index, value)
        finally:
            self._robot_edit_key = None

    def _end_gesture(self):
        if hasattr(self, "scene"):
            self.scene.end_gesture()
            self._sync_view()

    def _start_loader(self, path: Path, profile: bool):
        self._pending_model_path = path.resolve()
        super()._start_loader(path, profile)

    def _loaded(self, model, surfaces, settings=None):
        super()._loaded(model, surfaces, settings)
        self.current_source = (
            source_from_settings(settings, model)
            if settings is not None
            else RobotSource(
                kind="urdf", model_id=model.provenance.model_id, path=str(self._pending_model_path)
            )
        )
        self.current_source = self.current_source.model_copy(
            update={"fingerprint": model_fingerprint(model)}
        )
        self.scene.update_robot(self._capture_robot(), reset_history=True)
        self.scene_view.fit_all()
        self.append_log("로봇 모델 변경: 기존 Undo 이력 초기화, 작업환경 객체 유지")

    def _load_failed(self, message):
        super()._load_failed(message)
        if hasattr(self, "scene"):
            self._sync_view()

    def _scene_changed(self, change):
        document = self.scene.document
        if not self._syncing_to_scene:
            robot = document.robot
            self.base, self.tool_offset, self.tool_link = (
                robot.base,
                robot.tool_offset,
                robot.tool_link,
            )
            self.q = np.array(robot.joints.positions)
            self.tool_combo.blockSignals(True)
            self.tool_combo.setCurrentText(self.tool_link)
            self.tool_combo.blockSignals(False)
            with warnings.catch_warnings(record=True):
                rpy = Rotation.from_quat(robot.tool_offset.quaternion_xyzw).as_euler(
                    "xyz", degrees=True
                )
            values = [*(np.asarray(robot.tool_offset.position_m) * 1000), *rpy]
            for field, value in zip(self.tool_fields, values, strict=True):
                field.blockSignals(True)
                field.setValue(value)
                field.blockSignals(False)
            super().refresh_pose()
        ids = {str(o.id) for o in document.objects}
        if self.selected_id not in ids:
            self.selected_id = None
        signature = (
            document.robot.visible,
            tuple((str(o.id), o.name, o.kind, o.parent_frame, o.visible) for o in document.objects),
        )
        if signature != self._tree_signature:
            self._refresh_tree()
            self._tree_signature = signature
        self._sync_view()
        if not self.scene_view.dragging:
            self._update_editor()
        self.undo_action.setEnabled(self.scene.can_undo and not self.busy)
        self.redo_action.setEnabled(self.scene.can_redo and not self.busy)
        self.undo_action.setText(
            f"되돌리기 · {self.scene.undo_label}" if self.scene.can_undo else "되돌리기"
        )
        self.setWindowTitle(
            f"RobotStudio AI {__version__} · "
            + (self.project_path.name if self.project_path else "새 작업환경")
            + (" *" if self.scene.dirty else "")
        )
        self.statusBar().showMessage(
            f"객체 {len(document.objects)}개 · 충돌/경로 미검증"
            + (" · 변경됨" if self.scene.dirty else "")
        )

    def _sync_view(self, prepared=None):
        if not hasattr(self, "scene_view"):
            return
        transforms = self.scene.world_transforms(self.fk.tcp)
        self.scene_view.sync(
            self.scene.document,
            transforms,
            self.selected_id,
            self.manipulate.isChecked() and not self.busy,
            prepared,
        )

    def _refresh_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        document = self.scene.document
        root = QTreeWidgetItem(self.tree, [self.model.name])
        root.setData(0, Qt.ItemDataRole.UserRole, "robot")
        root.setCheckState(
            0, Qt.CheckState.Checked if document.robot.visible else Qt.CheckState.Unchecked
        )
        items = {self.model.root_link: root}
        for joint in self.model.joints:
            item = QTreeWidgetItem(items[joint.parent], [joint.child])
            item.setData(0, Qt.ItemDataRole.UserRole, f"link:{joint.child}")
            items[joint.child] = item
        group = QTreeWidgetItem(self.tree, [f"작업환경 객체 ({len(document.objects)})"])
        object_items = {}
        objects = {str(o.id): o for o in document.objects}

        def insert(key):
            if key not in object_items:
                obj = objects[key]
                parent = insert(obj.parent_frame) if obj.parent_frame in objects else group
                item = QTreeWidgetItem(parent, [obj.name])
                item.setData(0, Qt.ItemDataRole.UserRole, f"scene:{key}")
                item.setToolTip(0, f"{KINDS[obj.kind]} · {obj.id}")
                item.setCheckState(
                    0, Qt.CheckState.Checked if obj.visible else Qt.CheckState.Unchecked
                )
                object_items[key] = item
            return object_items[key]

        for key in objects:
            insert(key)
        self.tree.expandAll()
        if self.selected_id in object_items:
            self.tree.setCurrentItem(object_items[self.selected_id])
        elif self.selected_robot:
            self.tree.setCurrentItem(root)
        self.tree.blockSignals(False)

    def _tree_visibility(self, item, column):
        if self.busy:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        visible = item.checkState(0) == Qt.CheckState.Checked
        if key == "robot":
            self.scene.update_robot(
                self.scene.document.robot.model_copy(update={"visible": visible})
            )
        elif key and key.startswith("scene:"):
            obj = self.scene.get_object(key[6:])
            self.scene.update_object(obj.model_copy(update={"visible": visible}))

    def _select_link(self):
        if not hasattr(self, "scene"):
            return super()._select_link()
        if self._suspend_scene_sync:
            return
        selected = self.tree.selectedItems()
        key = selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else ""
        if key and key.startswith("scene:"):
            self.select_item(key[6:])
        elif key == "robot":
            self.select_item("robot")
        elif key and key.startswith("link:"):
            self.selected_id, self.selected_robot = None, False
            for (name, _), actor in self.viewport.actors.items():
                actor.prop.show_edges = name == key[5:]
            self._sync_view()
            self._update_editor()

    def select_item(self, key: str):
        self.scene.end_gesture()
        self.selected_robot = key == "robot"
        self.selected_id = key if key and key != "robot" else None
        if self.selected_id:
            try:
                self.scene.get_object(self.selected_id)
            except KeyError:
                self.selected_id = None
        for actor in self.viewport.actors.values():
            actor.prop.show_edges = False
        self._tree_signature = None
        self._refresh_tree()
        self._sync_view()
        self._update_editor()
        if self.selected_id or self.selected_robot:
            self.tabs.setCurrentIndex(2)

    def _update_editor(self):
        value = (
            self.scene.document.robot
            if self.selected_robot
            else self.scene.get_object(self.selected_id)
            if self.selected_id
            else None
        )
        self.editor.set_selection(value, self.scene.document)

    def apply_properties(self):
        if self.busy:
            return
        try:
            value = self.editor.edited_value()
            if isinstance(value, SceneRobot):
                self.scene.update_robot(value)
            else:
                self.scene.update_object(value)
        except (ValueError, KeyError) as error:
            self._show_error(str(error))

    def _object_transformed(self, key: str, world_matrix, gesture: str):
        if self.busy:
            return
        try:
            obj = self.scene.get_object(key)
            parent = self.scene.world_transforms(self.fk.tcp)[obj.parent_frame]
            pose = matrix_pose(np.linalg.inv(parent) @ world_matrix)
            self.scene.update_object(obj.model_copy(update={"pose": pose}), key=f"gizmo:{gesture}")
        except (ValueError, KeyError) as error:
            self.append_log(f"객체 변환 거부: {error}")

    def create_primitive(self, kind: str):
        if self.busy:
            return
        shapes = {
            "box": BoxShape(),
            "cylinder": CylinderShape(),
            "sphere": SphereShape(),
            "frame": FrameShape(),
        }
        labels = {"box": "상자", "cylinder": "원통", "sphere": "구", "frame": "좌표계"}
        obj = SceneObject(
            name=self.scene.unique_name(labels[kind]),
            shape=shapes[kind],
            pose=Pose(position_m=(0.5, 0, 0.05)),
            kind="coordinate_frame" if kind == "frame" else "obstacle",
            collision_enabled=kind != "frame",
        )
        self.scene.add(obj)
        self.select_item(str(obj.id))
        return obj.id

    def duplicate_selected(self):
        if self.selected_id and not self.busy:
            self.select_item(str(self.scene.duplicate(self.selected_id)))

    def delete_selected(self):
        if self.selected_id and not self.busy:
            self.scene.remove(self.selected_id)

    def load_demo(self):
        if self.busy:
            return
        document = self.scene.document
        robot = document.robot.model_copy(update={"base": Pose(position_m=(0, 0, 0.7))})
        objects = (
            SceneObject(
                name=self.scene.unique_name("예제 작업대"),
                kind="worktable",
                shape=BoxShape(size_m=(1.4, 1.0, 0.7)),
                pose=Pose(position_m=(0.45, 0, 0.35)),
                rgba=(0.30, 0.38, 0.46, 1.0),
            ),
            SceneObject(
                name=self.scene.unique_name("예제 상자"),
                kind="workpiece",
                shape=BoxShape(),
                pose=Pose(position_m=(0.65, -0.2, 0.75)),
                fixed=False,
                task_target=True,
                rgba=(0.94, 0.60, 0.22, 1.0),
            ),
            SceneObject(
                name=self.scene.unique_name("예제 원통"),
                kind="workpiece",
                shape=CylinderShape(height_m=0.12),
                pose=Pose(position_m=(0.65, 0.2, 0.76)),
                fixed=False,
                task_target=True,
                rgba=(0.31, 0.75, 0.65, 1.0),
            ),
            SceneObject(
                name=self.scene.unique_name("예제 장애물"),
                kind="obstacle",
                shape=BoxShape(size_m=(0.12, 0.3, 0.4)),
                pose=Pose(position_m=(1.0, 0, 0.9)),
                rgba=(0.82, 0.30, 0.38, 0.8),
            ),
            SceneObject(
                name=self.scene.unique_name("예제 목표"),
                kind="target",
                shape=FrameShape(),
                pose=Pose(position_m=(0.7, 0.35, 0.78)),
                collision_enabled=False,
            ),
        )
        self.scene.replace(
            document.model_copy(update={"robot": robot, "objects": document.objects + objects}),
            "예제 작업환경 추가",
        )
        self.select_item(str(objects[1].id))
        self.scene_view.fit_all()

    def import_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "환경 Mesh 가져오기", "", "Mesh (*.stl *.obj)")
        if not path:
            return
        units, accepted = QInputDialog.getItem(
            self, "Mesh 단위", "원본 파일의 거리 단위", ("mm", "m"), 0, False
        )
        if accepted:
            self.import_mesh_path(Path(path), units)

    def import_mesh_path(self, path: Path, units="mm"):
        def task():
            asset, center = import_mesh(path, self.cache_dir, units=units)
            surface = object_surface(MeshShape(asset_id=asset.id), (asset,))
            return asset, center, surface

        def ready(result):
            asset, center, surface = result
            obj = SceneObject(
                name=self.scene.unique_name(path.stem),
                shape=MeshShape(asset_id=asset.id),
                pose=Pose(position_m=center),
                properties={"source_file": path.name, "source_units": units},
            )
            self.scene_view.prepared[obj.shape.model_dump_json()] = surface
            self.scene.add(obj, asset)
            self.select_item(str(obj.id))
            self.scene_view.fit_all()

        self._run_job(task, ready)

    def camera_state(self) -> CameraState:
        camera = self.viewport.plotter.camera
        return CameraState(
            position=camera.position,
            focal_point=camera.focal_point,
            view_up=camera.up,
            parallel=camera.parallel_projection,
            view_angle_deg=camera.view_angle,
            parallel_scale_m=camera.parallel_scale,
        )

    def save_project_path(self, path: Path, continuation=None):
        snapshot = self.scene.document
        project = SceneProject(scene=snapshot, camera=self.camera_state())

        def ready(_):
            self.project_path = path.resolve()
            self.scene.mark_saved(snapshot)
            self._scene_changed(None)
            self.append_log(f"작업환경 저장: {path.name}")
            if continuation:
                continuation()

        self._run_job(lambda: save_project(path, project), ready)

    def load_project_path(self, path: Path):
        def task():
            project = load_project(path, self.cache_dir)
            settings, model = load_robot_source(project.scene.robot.source)
            robot = project.scene.robot
            if robot.joints.names != tuple(j.name for j in model.active_joints):
                raise ValueError("Project joint names do not match robot model")
            model.validate_positions(robot.joints.positions)
            if robot.tool_link not in model.links:
                raise ValueError("Project tool link is missing")
            surfaces = prepare_surfaces(model)
            objects = {
                str(o.id): object_surface(o.shape, project.scene.assets)
                for o in project.scene.objects
            }
            return project, settings, model, surfaces, objects

        def ready(result):
            project, settings, model, surfaces, objects = result
            self.current_source = project.scene.robot.source
            if settings is not None:
                self.settings = settings
            self.base, self.tool_offset = project.scene.robot.base, project.scene.robot.tool_offset
            home = (
                settings.robot.home_rad
                if settings
                else tuple(
                    min(
                        j.upper if j.upper is not None else np.inf,
                        max(j.lower if j.lower is not None else -np.inf, 0.0),
                    )
                    for j in model.active_joints
                )
            )
            self.apply_model(model, surfaces, home, project.scene.robot.tool_link)
            self.scene_view.stage_surfaces(project.scene, objects)
            self.project_path = path.resolve()
            self.scene.reset(project.scene)
            self._sync_view(objects)
            if project.camera:
                camera = self.viewport.plotter.camera
                camera.position, camera.focal_point, camera.up = (
                    project.camera.position,
                    project.camera.focal_point,
                    project.camera.view_up,
                )
                camera.parallel_projection = project.camera.parallel
                camera.view_angle = project.camera.view_angle_deg
                camera.parallel_scale = project.camera.parallel_scale_m
                self.viewport.plotter.renderer.ResetCameraClippingRange()
                self.viewport.plotter.render()
            self.append_log(f"작업환경 불러오기: {path.name}")

        self._run_job(task, ready)

    def _run_job(self, task, on_ready):
        if self.busy:
            return
        job = ResourceJob(task)
        state = {}
        self._extra_jobs.append(job)
        self._set_busy(True)
        job.signals.ready.connect(lambda value: state.update(result=value))
        job.signals.failed.connect(lambda message: state.update(error=message))

        def finished():
            self._extra_jobs.remove(job)
            self._set_busy(False)
            if "error" in state:
                self._show_error(state["error"])
            else:
                try:
                    on_ready(state.get("result"))
                except Exception as error:
                    LOGGER.exception("Scene UI operation failed")
                    self._show_error(str(error))

        job.signals.finished.connect(finished)
        self.pool.start(job)

    def _set_busy(self, value):
        self.busy = value
        for widget in (
            self.model_selector,
            self.open_button,
            self.tree,
            self.joint_scroll,
            self.frame_panel,
            self.editor.apply_button,
            *self.environment_buttons,
        ):
            widget.setEnabled(not value)
        self.undo_action.setEnabled(not value and self.scene.can_undo)
        self.redo_action.setEnabled(not value and self.scene.can_redo)
        self._sync_view()
        if value:
            self.statusBar().showMessage("작업환경 파일 처리 중…")

    def _show_error(self, message):
        self.append_log(f"작업환경 오류: {message}")
        QMessageBox.warning(self, "작업환경 오류", message)

    def _guard_unsaved(self, continuation):
        if self.busy:
            return
        if not self.scene.dirty:
            continuation()
            return
        answer = QMessageBox.question(
            self,
            "저장하지 않은 변경",
            "현재 작업환경을 저장할까요?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Discard:
            continuation()
        elif answer == QMessageBox.StandardButton.Save:
            self._save_dialog(continuation=continuation)

    def save_dialog(self):
        self._save_dialog()

    def save_as_dialog(self):
        self._save_dialog(force=True)

    def _save_dialog(self, force=False, continuation=None):
        if self.busy:
            return
        path = self.project_path
        if path is None or force:
            filename, _ = QFileDialog.getSaveFileName(
                self, "작업환경 저장", str(path or "작업환경.rsai"), "RobotStudio AI (*.rsai)"
            )
            if not filename:
                return
            path = Path(filename)
            if path.suffix.lower() != ".rsai":
                path = path.with_suffix(".rsai")
        self.save_project_path(path, continuation)

    def open_project_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "작업환경 열기", "", "RobotStudio AI (*.rsai)"
        )
        if filename:
            self._guard_unsaved(lambda: self.load_project_path(Path(filename)))

    def new_scene_dialog(self):
        def reset():
            self.scene.reset(SceneDocument(robot=self._capture_robot()))
            self.project_path = None
            self._scene_changed(None)

        self._guard_unsaved(reset)

    def closeEvent(self, event: QCloseEvent):
        if self.closed:
            event.accept()
            return
        if self.busy:
            event.ignore()
            return
        if hasattr(self, "scene") and self.scene.dirty:
            event.ignore()
            self._guard_unsaved(lambda: (self.scene.mark_saved(), self.close()))
            return
        if hasattr(self, "scene_view"):
            self.scene_view.clear_widget()
        super().closeEvent(event)
