"""Validated scene property editor: display mm/degrees, commit SI records."""

import json
import warnings

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from scipy.spatial.transform import Rotation

from robotstudio_ai.core.scene import (
    BoxShape,
    CylinderShape,
    FrameShape,
    SceneDocument,
    SceneObject,
    SceneRobot,
    SphereShape,
)
from robotstudio_ai.core.schema import Pose

KINDS = {
    "worktable": "작업대",
    "workpiece": "공작물",
    "obstacle": "장애물",
    "gripper": "그리퍼",
    "pallet": "팔레트",
    "conveyor": "컨베이어",
    "jig": "지그",
    "fence": "펜스",
    "target": "목표",
    "coordinate_frame": "좌표계",
    "forbidden_zone": "진입 금지 영역",
    "custom": "기타",
}


def spin(minimum=-1e8, maximum=1e8, suffix=" mm", decimals=3):
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setDecimals(decimals)
    field.setSuffix(suffix)
    field.setKeyboardTracking(False)
    return field


class PoseEditor(QWidget):
    def __init__(self):
        super().__init__()
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.fields = []
        for i, axis in enumerate(("X", "Y", "Z", "Roll", "Pitch", "Yaw")):
            field = spin(suffix=" mm" if i < 3 else " °", decimals=6)
            if i >= 3:
                field.setRange(-180, 180)
            self.fields.append(field)
            form.addRow(axis, field)
        self.set_pose(Pose())

    def set_pose(self, pose: Pose):
        with warnings.catch_warnings(record=True):
            angles = Rotation.from_quat(pose.quaternion_xyzw).as_euler("xyz", degrees=True)
        for field, value in zip(
            self.fields, [*(np.asarray(pose.position_m) * 1000), *angles], strict=True
        ):
            field.setValue(float(value))
        self._pose = pose
        self._display = tuple(f.value() for f in self.fields)

    def value(self) -> Pose:
        values = tuple(f.value() for f in self.fields)
        if values == self._display:
            return self._pose
        return Pose(
            position_m=tuple(v / 1000 for v in values[:3]),
            quaternion_xyzw=tuple(Rotation.from_euler("xyz", values[3:], degrees=True).as_quat()),
        )


class ObjectEditor(QWidget):
    apply_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.heading = QLabel("객체를 선택하세요")
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        form = QFormLayout()
        self.name = QLineEdit()
        form.addRow("이름", self.name)
        self.kind = QComboBox()
        for key, label in KINDS.items():
            self.kind.addItem(label, key)
        form.addRow("종류", self.kind)
        self.parent_frame = QComboBox()
        form.addRow("부모 좌표계", self.parent_frame)
        layout.addLayout(form)
        note = QLabel("위치·자세는 선택한 부모 기준입니다.")
        note.setObjectName("muted")
        layout.addWidget(note)
        self.pose = PoseEditor()
        layout.addWidget(self.pose)
        sizes = QFormLayout()
        self.size_fields, self.size_labels = [], []
        for _ in range(3):
            label, field = QLabel(), spin(0.000001, 1e8)
            sizes.addRow(label, field)
            self.size_fields.append(field)
            self.size_labels.append(label)
        self.mass = spin(0, 1e8, " kg", 6)
        sizes.addRow("질량", self.mass)
        layout.addLayout(sizes)
        self.visible = QCheckBox("표시")
        self.collision = QCheckBox("충돌 검사 대상")
        self.collision.setToolTip(
            "검사 대상 플래그만 저장합니다. 충돌 계산은 Phase 3에서 구현합니다."
        )
        self.fixed = QCheckBox("고정 객체")
        self.target = QCheckBox("작업 대상")
        for field in (self.visible, self.collision, self.fixed, self.target):
            layout.addWidget(field)
        self.colour_button = QPushButton("색상 선택…")
        self.colour_button.clicked.connect(self._choose_colour)
        layout.addWidget(self.colour_button)
        layout.addWidget(QLabel("사용자 속성 · JSON"))
        self.properties = QPlainTextEdit()
        self.properties.setFixedHeight(70)
        layout.addWidget(self.properties)
        self.apply_button = QPushButton("변경 적용")
        self.apply_button.clicked.connect(self.apply_requested)
        layout.addWidget(self.apply_button)
        layout.addStretch()
        self.rgba = (0.4, 0.7, 0.8, 1.0)
        self.current = None
        self.setEnabled(False)

    def _choose_colour(self):
        current = QColor.fromRgbF(*self.rgba)
        selected = QColorDialog.getColor(
            current, self, "객체 색상", QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if selected.isValid():
            self.rgba = selected.getRgbF()
            self._show_colour()

    def _show_colour(self):
        colour = QColor.fromRgbF(*self.rgba)
        self.colour_button.setText(f"색상  {colour.name()}  ·  불투명도 {self.rgba[3]:.2f}")

    def set_selection(self, value: SceneObject | SceneRobot | None, document: SceneDocument):
        self.current = value
        self.setEnabled(value is not None)
        self.apply_button.setEnabled(value is not None)
        if value is None:
            self.heading.setText("장면 객체 또는 로봇을 선택하세요")
            return
        is_robot = isinstance(value, SceneRobot)
        self.heading.setText(f"{'로봇 Base' if is_robot else '객체'} · {str(value.id)[:8]}")
        self.heading.setToolTip(str(value.id))
        self.name.setText(value.source.model_id if is_robot else value.name)
        self.name.setReadOnly(is_robot)
        for field in (
            self.kind,
            self.parent_frame,
            self.mass,
            self.collision,
            self.fixed,
            self.target,
            self.colour_button,
            self.properties,
        ):
            field.setEnabled(not is_robot)
        self.parent_frame.clear()
        self.parent_frame.addItem("World", "world")
        self.parent_frame.addItem("로봇 Base", "robot_base")
        self.parent_frame.addItem("로봇 Tool/TCP", "robot_tool")
        for obj in document.objects:
            if obj.id != value.id:
                self.parent_frame.addItem(obj.name, str(obj.id))
        self.pose.set_pose(value.base if is_robot else value.pose)
        self.visible.setChecked(value.visible)
        for field, label in zip(self.size_fields, self.size_labels, strict=True):
            field.setVisible(False)
            label.setVisible(False)
        if is_robot:
            self.properties.setPlainText("{}")
            return
        self.kind.setCurrentIndex(self.kind.findData(value.kind))
        self.parent_frame.setCurrentIndex(self.parent_frame.findData(value.parent_frame))
        self.mass.setValue(value.mass_kg)
        self.collision.setChecked(value.collision_enabled)
        self.fixed.setChecked(value.fixed)
        self.target.setChecked(value.task_target)
        self.rgba = value.rgba
        self._show_colour()
        self.properties.setPlainText(json.dumps(value.properties, ensure_ascii=False, indent=2))
        shape = value.shape
        if isinstance(shape, BoxShape):
            params, labels, factor = shape.size_m, ("크기 X", "크기 Y", "크기 Z"), 1000
        elif isinstance(shape, CylinderShape):
            params, labels, factor = (shape.radius_m, shape.height_m), ("반지름", "높이"), 1000
        elif isinstance(shape, SphereShape):
            params, labels, factor = (shape.radius_m,), ("반지름",), 1000
        elif isinstance(shape, FrameShape):
            params, labels, factor = (shape.size_m,), ("축 길이",), 1000
        else:
            params, labels, factor = shape.scale, ("배율 X", "배율 Y", "배율 Z"), 1
        for field, label, value, text in zip(
            self.size_fields, self.size_labels, params, labels, strict=False
        ):
            field.setVisible(True)
            label.setVisible(True)
            field.setSuffix(" mm" if factor == 1000 else " ×")
            field.setValue(value * factor)
            label.setText(text)

    def edited_value(self) -> SceneObject | SceneRobot:
        value = self.current
        if isinstance(value, SceneRobot):
            return SceneRobot.model_validate(
                value.model_dump()
                | {"base": self.pose.value(), "visible": self.visible.isChecked()}
            )
        if not isinstance(value, SceneObject):
            raise ValueError("Select a scene object")
        dimensions = [f.value() / 1000 for f in self.size_fields]
        if isinstance(value.shape, BoxShape):
            shape = BoxShape(size_m=tuple(dimensions))
        elif isinstance(value.shape, CylinderShape):
            shape = CylinderShape(radius_m=dimensions[0], height_m=dimensions[1])
        elif isinstance(value.shape, SphereShape):
            shape = SphereShape(radius_m=dimensions[0])
        elif isinstance(value.shape, FrameShape):
            shape = FrameShape(size_m=dimensions[0])
        else:
            shape = value.shape.model_copy(
                update={"scale": tuple(f.value() for f in self.size_fields)}
            )
        properties = json.loads(self.properties.toPlainText())
        return SceneObject.model_validate(
            value.model_dump()
            | dict(
                name=self.name.text().strip(),
                kind=self.kind.currentData(),
                shape=shape,
                parent_frame=self.parent_frame.currentData(),
                pose=self.pose.value(),
                mass_kg=self.mass.value(),
                visible=self.visible.isChecked(),
                collision_enabled=self.collision.isChecked(),
                fixed=self.fixed.isChecked(),
                task_target=self.target.isChecked(),
                rgba=self.rgba,
                properties=properties,
            )
        )
