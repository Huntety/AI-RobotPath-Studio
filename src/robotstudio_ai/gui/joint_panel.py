"""SI joint values with synchronized degree/mm spin boxes and sliders."""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from robotstudio_ai.core.robot_model import Joint


class JointControl(QWidget):
    """Bounded control. Continuous joints use a visible one-turn jog window."""

    changed = Signal(float)

    def __init__(self, joint: Joint, parent: QWidget | None = None):
        super().__init__(parent)
        self.joint = joint
        self.factor = 1000.0 if joint.kind == "prismatic" else 180 / math.pi
        low = -math.pi if joint.lower is None else joint.lower
        high = math.pi if joint.upper is None else joint.upper
        self.low, self.high = low, high
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        row = QHBoxLayout()
        row.addWidget(QLabel(joint.name), 1)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(3)
        self.spin.setRange(low * self.factor, high * self.factor)
        self.spin.setSuffix(" mm" if joint.kind == "prismatic" else " °")
        self.spin.setSingleStep(1)
        self.spin.setKeyboardTracking(False)
        self.spin.setMinimumWidth(124)
        row.addWidget(self.spin)
        layout.addLayout(row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 10000)
        layout.addWidget(self.slider)
        limit_text = f"{low * self.factor:.1f}  ↔  {high * self.factor:.1f}" + (
            "  · continuous jog window" if joint.kind == "continuous" else ""
        )
        self.setToolTip(limit_text)
        self.slider.valueChanged.connect(self._slider_changed)
        self.spin.valueChanged.connect(self._spin_changed)

    def set_value(self, value: float):
        """Update presentation without feeding rounded display values back into FK."""
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(round((value - self.low) / (self.high - self.low) * 10000))
        self.spin.setValue(value * self.factor)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def _slider_changed(self, value: int):
        position = self.low + value / 10000 * (self.high - self.low)
        self.set_value(position)
        self.changed.emit(position)

    def _spin_changed(self, value: float):
        position = min(self.high, max(self.low, value / self.factor))
        self.set_value(position)
        self.changed.emit(position)
