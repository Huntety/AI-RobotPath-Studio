"""Phase 3 user controls; calculations remain in the core and worker jobs."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from robotstudio_ai.gui.object_editor import PoseEditor, spin


class PlanningPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("목표 TCP · World 기준 mm / degree")
        title.setWordWrap(True)
        layout.addWidget(title)
        row = QHBoxLayout()
        self.from_current = QPushButton("현재 TCP")
        self.from_object = QPushButton("선택 객체")
        row.addWidget(self.from_current)
        row.addWidget(self.from_object)
        layout.addLayout(row)
        self.goal = PoseEditor()
        layout.addWidget(self.goal)
        self.collision_filter = QCheckBox("충돌·여유거리 통과 후보만 찾기")
        self.collision_filter.setChecked(True)
        layout.addWidget(self.collision_filter)
        row = QHBoxLayout()
        self.solve = QPushButton("IK 계산")
        self.apply = QPushButton("후보 자세 적용")
        self.apply.setEnabled(False)
        row.addWidget(self.solve)
        row.addWidget(self.apply)
        layout.addLayout(row)
        self.ik_status = QLabel("목표를 지정하고 IK를 계산하세요.")
        self.ik_status.setWordWrap(True)
        self.ik_status.setTextInteractionFlags(self.ik_status.textInteractionFlags())
        layout.addWidget(self.ik_status)
        form = QFormLayout()
        self.margin = spin(0, 1000, " mm", 3)
        self.resolution = spin(0.1, 100, " mm", 3)
        form.addRow("안전 여유거리", self.margin)
        form.addRow("구간 이동량 간격", self.resolution)
        layout.addLayout(form)
        self.fallback = QCheckBox("누락된 로봇 충돌 형상에 CAD 외형 근사 사용")
        self.fallback.setToolTip(
            "제조사 검증 형상이 아닙니다. 메시의 convex hull을 사용해 과검출할 수 있습니다."
        )
        layout.addWidget(self.fallback)
        note = QLabel(
            "메시: 보수적 convex hull · S922: 제어기 좌표 미보정\n"
            "검사 통과는 실제 로봇 안전 인증이 아닙니다."
        )
        note.setWordWrap(True)
        note.setObjectName("warning")
        layout.addWidget(note)
        self.policy_apply = QPushButton("검사 설정 적용 · 프로젝트에 저장")
        layout.addWidget(self.policy_apply)
        row = QHBoxLayout()
        self.check_pose = QPushButton("현재 자세 검사")
        self.capture_start = QPushButton("시작 자세 기억")
        row.addWidget(self.check_pose)
        row.addWidget(self.capture_start)
        layout.addLayout(row)
        self.start_status = QLabel("구간 시작 자세가 없습니다.")
        self.start_status.setWordWrap(True)
        layout.addWidget(self.start_status)
        self.check_edge = QPushButton("기억한 시작 → 현재 자세 구간 검사")
        layout.addWidget(self.check_edge)
        self.status = QLabel("장면 검사 전 · 자동 재검사는 수행하지 않습니다.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.pairs = QTreeWidget()
        self.pairs.setHeaderLabels(["대상 A", "대상 B", "거리 mm"])
        self.pairs.setMinimumHeight(115)
        self.pairs.setMaximumHeight(180)
        layout.addWidget(self.pairs)
        layout.addWidget(QLabel("허용 충돌 쌍 · 지정한 쌍은 검사에서 제외"))
        self.allow_a, self.allow_b = QComboBox(), QComboBox()
        layout.addWidget(self.allow_a)
        layout.addWidget(self.allow_b)
        row = QHBoxLayout()
        self.allow_add = QPushButton("허용 쌍 추가")
        self.allow_remove = QPushButton("선택 허용 쌍 삭제")
        row.addWidget(self.allow_add)
        row.addWidget(self.allow_remove)
        layout.addLayout(row)
        self.allowed = QListWidget()
        self.allowed.setFixedHeight(70)
        layout.addWidget(self.allowed)
        layout.addStretch()
