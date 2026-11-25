"""Phase 1 desktop robot model workbench; contains no robot transport or export."""

import logging
import warnings
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from scipy.spatial.transform import Rotation

from robotstudio_ai import __version__
from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.robot_model import RobotModel
from robotstudio_ai.core.schema import Pose
from robotstudio_ai.core.urdf import load_urdf
from robotstudio_ai.gui.joint_panel import JointControl
from robotstudio_ai.gui.viewport import RobotViewport, Surfaces, prepare_surfaces
from robotstudio_ai.settings import AppSettings, load_settings

LOGGER = logging.getLogger(__name__)


class LoaderSignals(QObject):
    ready = Signal(object, object)
    failed = Signal(str)
    finished = Signal()


class ModelLoader(QRunnable):
    """Load and validate URDF/mesh without blocking Qt input or rendering."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.signals = LoaderSignals()

    def run(self):
        try:
            model = load_urdf(self.path)
            surfaces = prepare_surfaces(model)
            self.signals.ready.emit(model, surfaces)
        except Exception as error:
            LOGGER.exception("URDF load failed")
            self.signals.failed.emit(str(error))
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    """One validated joint vector drives FK, VTK actors, TCP and matrix readouts."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        model: RobotModel | None = None,
        off_screen: bool = False,
    ):
        super().__init__()
        if settings is None or model is None:
            settings, model = load_settings()
        self.settings = settings
        self.solver = TreeKinematics()
        self.base = settings.robot.base
        self.tool_offset = settings.robot.tool_offset
        self.pool = QThreadPool(self)
        self.jobs: list[ModelLoader] = []
        self.closed = False
        self.busy = False
        self.setWindowTitle(f"RobotStudio AI {__version__} | 오프라인 로봇 모델")
        self.resize(1500, 980)
        self.setMinimumSize(1100, 760)
        self.setFont(QFont("Malgun Gothic", 9))
        self.setStyleSheet(STYLE)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.matrix_view = QPlainTextEdit()
        self.matrix_view.setReadOnly(True)
        self.matrix_view.setFont(QFont("Consolas", 10))
        self._build_layout(off_screen)
        self._build_menu()
        self.apply_model(
            model, prepare_surfaces(model), settings.robot.home_rad, settings.robot.tool_link
        )

    def _build_layout(self, off_screen: bool):
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(18, 12, 18, 12)
        header = QHBoxLayout()
        title = QLabel("ROBOTSTUDIO  <span style='color:#58c7db'>AI</span>")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.model_badge = QLabel()
        self.model_badge.setObjectName("badge")
        header.addWidget(self.model_badge)
        layout.addLayout(header)
        toolbar = QHBoxLayout()
        self.open_button = QPushButton("URDF 열기")
        self.open_button.clicked.connect(self.open_urdf)
        toolbar.addWidget(self.open_button)
        for text, callback in (
            ("Home 자세", self.reset_home),
            ("제로 자세", self.reset_zero),
            ("화면 맞춤", lambda: self.viewport.fit()),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addStretch()
        self.axes_toggle = QCheckBox("Base / Tool / TCP 좌표축")
        self.axes_toggle.setChecked(True)
        toolbar.addWidget(self.axes_toggle)
        layout.addLayout(toolbar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setIndentation(10)
        self.tree.setHeaderLabel("로봇 구조")
        self.tree.setMinimumWidth(165)
        self.tree.itemSelectionChanged.connect(self._select_link)
        splitter.addWidget(self.tree)
        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        self.viewport = RobotViewport(off_screen=off_screen)
        middle_layout.addWidget(self.viewport, 1)
        hint = QLabel(
            "드래그: 회전  ·  Shift + 드래그: 이동  ·  휠: 확대/축소   |   X 빨강  Y 초록  Z 파랑"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        middle_layout.addWidget(hint)
        splitter.addWidget(middle)
        panel = QWidget()
        panel.setMinimumWidth(310)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(370)
        self.joint_scroll = QScrollArea()
        self.joint_scroll.setWidgetResizable(True)
        self.tabs.addTab(self.joint_scroll, "관절 조작")
        self.frame_panel = QWidget()
        form = QFormLayout(self.frame_panel)
        self.tool_combo = QComboBox()
        self.tool_combo.currentTextChanged.connect(self._change_tool_link)
        form.addRow("Tool 링크", self.tool_combo)
        self.tool_fields: list[QDoubleSpinBox] = []
        for index, axis in enumerate(("X", "Y", "Z", "Roll", "Pitch", "Yaw")):
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setRange(-10000 if index < 3 else -180, 10000 if index < 3 else 180)
            spin.setSuffix(" mm" if index < 3 else " °")
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._change_tool_offset)
            self.tool_fields.append(spin)
            form.addRow(axis, spin)
        note = QLabel("선택한 Tool 링크 기준 TCP 오프셋\n회전: 고정축 X → Y → Z")
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)
        self.tabs.addTab(self.frame_panel, "TCP 설정")
        panel_layout.addWidget(self.tabs, 1)
        tcp = QGroupBox("TCP · World 기준")
        tcp_layout = QVBoxLayout(tcp)
        self.tcp_position = QLabel()
        self.tcp_position.setObjectName("readout")
        self.tcp_orientation = QLabel()
        self.tcp_orientation.setWordWrap(True)
        self.tcp_quaternion = QLabel()
        self.tcp_quaternion.setObjectName("muted")
        self.tcp_quaternion.setWordWrap(True)
        tcp_layout.addWidget(self.tcp_position)
        tcp_layout.addWidget(self.tcp_orientation)
        tcp_layout.addWidget(self.tcp_quaternion)
        panel_layout.addWidget(tcp)
        warning = QLabel("모델 자세 확인용 · 충돌/경로 미검증\n실제 로봇 연결 및 구동 기능 없음")
        warning.setObjectName("notice")
        warning.setWordWrap(True)
        panel_layout.addWidget(warning)
        splitter.addWidget(panel)
        splitter.setSizes([180, 900, 340])
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(shell)
        self.axes_toggle.toggled.connect(self.viewport.show_frames)
        dock = QDockWidget("검증 및 시스템 정보", self)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setMinimumHeight(100)
        bottom = QTabWidget()
        bottom.addTab(self.log, "시스템 로그")
        bottom.addTab(self.matrix_view, "TCP 변환행렬")
        dock.setWidget(bottom)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [130], Qt.Orientation.Vertical)
        self.info_dock = dock

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("파일")
        action = QAction("URDF 열기…", self)
        action.setShortcut("Ctrl+O")
        action.triggered.connect(self.open_urdf)
        file_menu.addAction(action)
        close = file_menu.addAction("종료")
        close.triggered.connect(self.close)
        view = self.menuBar().addMenu("보기")
        view.addAction(self.info_dock.toggleViewAction())
        view.addAction("화면 맞춤", lambda: self.viewport.fit())
        help_menu = self.menuBar().addMenu("도움말")
        help_menu.addAction(
            "현재 구현 범위",
            lambda: QMessageBox.information(
                self,
                "Phase 1",
                "URDF 모델, 수동 관절 조작, FK, TCP/좌표계 표시를 제공합니다.\n"
                "Generic 모델은 자체 제작 테스트 모델이며 HITBOT S922 사양이 아닙니다.\n"
                "IK·충돌·경로·동역학·LLM·로봇 코드 출력은 이후 단계입니다.",
            ),
        )

    def apply_model(
        self, model: RobotModel, surfaces: Surfaces, home: tuple[float, ...], tool_link: str
    ):
        """Commit a fully loaded model to the UI; no source files are modified."""
        model.validate_positions(home)
        self.model = model
        self.home = tuple(home)
        self.q = np.asarray(home, dtype=float)
        self.tool_link = tool_link
        self.model_badge.setText(model.provenance.display_name)
        self.model_badge.setToolTip(model.provenance.source)
        joint_widget = QWidget()
        joint_layout = QVBoxLayout(joint_widget)
        self.controls: list[JointControl] = []
        for index, joint in enumerate(model.active_joints):
            control = JointControl(joint)
            control.changed.connect(lambda value, i=index: self.set_joint(i, value))
            joint_layout.addWidget(control)
            self.controls.append(control)
        joint_layout.addStretch()
        self.joint_scroll.setWidget(joint_widget)
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        self.tool_combo.addItems(list(model.links))
        self.tool_combo.setCurrentText(tool_link)
        self.tool_combo.blockSignals(False)
        rpy = Rotation.from_quat(self.tool_offset.quaternion_xyzw).as_euler("xyz", degrees=True)
        values = [*(np.asarray(self.tool_offset.position_m) * 1000), *rpy]
        for field, value in zip(self.tool_fields, values, strict=True):
            field.blockSignals(True)
            field.setValue(value)
            field.blockSignals(False)
        self.tree.clear()
        root = QTreeWidgetItem(self.tree, [model.name])
        root.setData(0, Qt.ItemDataRole.UserRole, model.root_link)
        items = {model.root_link: root}
        for joint in model.joints:
            item = QTreeWidgetItem(items[joint.parent], [joint.child])
            item.setData(0, Qt.ItemDataRole.UserRole, joint.child)
            item.setToolTip(0, f"{joint.name} · {joint.kind}")
            items[joint.child] = item
        self.tree.expandAll()
        self.viewport.set_model(model, surfaces, self.settings.frame_size_m)
        self.refresh_pose()
        self.viewport.fit()
        self.append_log(
            f"모델 로드: {model.provenance.display_name} | "
            f"{len(model.active_joints)} joints / {len(model.links)} links"
        )

    def refresh_pose(self):
        self.fk = self.solver.forward(
            self.model, self.q, self.tool_link, self.base, self.tool_offset
        )
        self.viewport.update_pose(self.fk, self.model.root_link, self.tool_link)
        for control, value in zip(self.controls, self.q, strict=True):
            control.set_value(value)
        xyz = self.fk.tcp[:3, 3] * 1000
        rotation = Rotation.from_matrix(self.fk.tcp[:3, :3])
        with warnings.catch_warnings(record=True) as caught:
            rpy = rotation.as_euler("xyz", degrees=True)
        self.tcp_position.setText(f"X  {xyz[0]:9.3f} mm\nY  {xyz[1]:9.3f} mm\nZ  {xyz[2]:9.3f} mm")
        self.tcp_orientation.setText(
            "RPY  "
            + "  /  ".join(f"{v:.2f}°" for v in rpy)
            + ("\nEuler 특이점: quaternion 참고" if caught else "")
        )
        self.tcp_quaternion.setText(
            "q (xyzw)  " + "  ".join(f"{v:.4f}" for v in rotation.as_quat())
        )
        self.matrix_view.setPlainText(
            "T_world_tcp  ·  m\n" + np.array2string(self.fk.tcp, precision=7, suppress_small=True)
        )
        self.statusBar().showMessage(f"{self.model.name}  |  {len(self.q)} DOF  |  FK 표시 갱신")

    def set_joint(self, index: int, value: float):
        """Validate before mutating the current state (also used by GUI tests)."""
        proposed = self.q.copy()
        proposed[index] = value
        self.model.validate_positions(proposed)
        self.q = proposed
        self.refresh_pose()

    def reset_home(self):
        self.q = np.asarray(self.home, dtype=float)
        self.refresh_pose()
        self.append_log("Home 자세로 복원")

    def reset_zero(self):
        proposed = tuple(
            min(
                j.upper if j.upper is not None else np.inf,
                max(j.lower if j.lower is not None else -np.inf, 0.0),
            )
            for j in self.model.active_joints
        )
        self.q = np.asarray(self.model.validate_positions(proposed))
        self.refresh_pose()
        self.append_log("제로 자세 (관절 제한 내 값 적용)")

    def _change_tool_link(self, text: str):
        if text and hasattr(self, "model"):
            self.tool_link = text
            self.refresh_pose()

    def _change_tool_offset(self):
        values = [field.value() for field in self.tool_fields]
        self.tool_offset = Pose(
            position_m=tuple(v / 1000 for v in values[:3]),
            quaternion_xyzw=tuple(Rotation.from_euler("xyz", values[3:], degrees=True).as_quat()),
        )
        if hasattr(self, "model"):
            self.refresh_pose()

    def _select_link(self):
        selected = self.tree.selectedItems()
        link = selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None
        if hasattr(self, "viewport"):
            for (name, _), actor in self.viewport.actors.items():
                actor.prop.show_edges = name == link
                actor.prop.edge_color = "#58c7db"
            self.viewport.plotter.render()

    def open_urdf(self):
        if self.busy:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "URDF 열기", "", "Robot model (*.urdf)")
        if filename:
            self.load_urdf_async(Path(filename))

    def load_urdf_async(self, path: Path):
        if self.busy:
            return
        self.busy = True
        self.open_button.setEnabled(False)
        self.statusBar().showMessage("URDF와 mesh를 불러오는 중…")
        loader = ModelLoader(path)
        loader.signals.ready.connect(self._loaded)
        loader.signals.failed.connect(self._load_failed)
        loader.signals.finished.connect(lambda: self._load_finished(loader))
        self.jobs.append(loader)
        self.pool.start(loader)

    def _loaded(self, model: RobotModel, surfaces: Surfaces):
        if self.closed:
            return
        home = tuple(
            min(
                j.upper if j.upper is not None else np.inf,
                max(j.lower if j.lower is not None else -np.inf, 0.0),
            )
            for j in model.active_joints
        )
        tool = (
            "tool0"
            if "tool0" in model.links
            else (model.joints[-1].child if model.joints else model.root_link)
        )
        self.tool_offset = Pose()
        self.apply_model(model, surfaces, home, tool)

    def _load_failed(self, message: str):
        if not self.closed:
            self.append_log(f"로드 실패 (기존 모델 유지): {message}")
            QMessageBox.warning(self, "URDF 로드 실패", message)

    def _load_finished(self, loader: ModelLoader):
        self.jobs.remove(loader)
        self.busy = False
        self.open_button.setEnabled(True)

    def append_log(self, text: str):
        LOGGER.info(text)
        self.log.appendPlainText(text)

    def closeEvent(self, event: QCloseEvent):
        self.closed = True
        self.viewport.close_view()
        super().closeEvent(event)


STYLE = """
QMainWindow, QWidget {background:#131e2b; color:#dfe8f2;}
QMenuBar, QMenu {background:#101925;}
QMenu::item:selected {background:#2b465e;}
QLabel#title {font-size:24px; font-weight:700; letter-spacing:1px;}
QLabel#badge {color:#6ed3e3; background:#183342; border:1px solid #2c5667;
  border-radius:5px; padding:7px 12px;}
QLabel#muted {color:#91a7bd; font-size:11px;}
QLabel#readout {font-family:Consolas; font-size:17px; color:#8ee4d2; padding:5px;}
QLabel#notice {color:#dec18a; background:#302c26; border-radius:5px; padding:9px;}
QPushButton {background:#23374b; border:1px solid #3b536b; border-radius:5px;
  padding:7px 13px;}
QPushButton:hover {background:#304e65; border-color:#58c7db;}
QPushButton:disabled {color:#71869b;}
QDoubleSpinBox, QComboBox {background:#0d1825; border:1px solid #3b536b;
  border-radius:4px; padding:5px; min-height:20px;}
QTreeWidget, QPlainTextEdit, QScrollArea {background:#101b28; border:1px solid #2b3e52;}
QTreeWidget::item {padding:4px 0;}
QTreeWidget::item:selected {background:#25516a;}
QHeaderView::section {background:#223348; padding:8px; border:0;}
QGroupBox {border:1px solid #344a60; border-radius:5px; margin-top:12px; padding-top:10px;}
QGroupBox::title {subcontrol-origin:margin; padding:0 6px; color:#9cbed4;}
QTabWidget::pane {border:1px solid #2b3e52;}
QTabBar::tab {background:#1c2b3c; padding:8px 13px; color:#9fb3c7;}
QTabBar::tab:selected {background:#29465b; color:#8fe3ef; border-bottom:2px solid #58c7db;}
QSlider::groove:horizontal {height:5px; background:#30465b; border-radius:2px;}
QSlider::sub-page:horizontal {background:#408fa8;}
QSlider::handle:horizontal {background:#7ed9e3; width:13px; margin:-5px 0; border-radius:6px;}
QSplitter::handle {background:#25384b; width:4px;}
QStatusBar {background:#0c1722; color:#8da7bf;}
QDockWidget::title {background:#1c2c3d; padding:5px;}
"""
