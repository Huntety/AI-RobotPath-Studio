"""Revision-aware Phase 3 analyses and red geometry/contact overlays."""

import math

import numpy as np
import pyvista as pv
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QScrollArea, QTreeWidgetItem

from robotstudio_ai.core.collision import FCLSceneChecker
from robotstudio_ai.core.collision_settings import CollisionSettings
from robotstudio_ai.core.inverse_kinematics import BoundedIK
from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.scene import SceneManager
from robotstudio_ai.core.schema import JointState
from robotstudio_ai.core.transforms import matrix_pose
from robotstudio_ai.gui.planning_panel import PlanningPanel
from robotstudio_ai.gui.workbench import SceneWorkbench


class PlanningWorkbench(SceneWorkbench):
    def __init__(self, *args, **kwargs):
        self.ik_result = None
        self.ik_token = None
        self.collision_report = None
        self.edge_report = None
        self.edge_start = None
        self.overlays = []
        self._policy_signature = None
        super().__init__(*args, **kwargs)
        self.analysis = PlanningPanel()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.analysis)
        self.tabs.addTab(scroll, "IK / 충돌")
        self.tabs.currentChanged.connect(lambda i: self.tcp_group.setVisible(i < 2))
        self.analysis.goal.set_pose(matrix_pose(self.fk.tcp))
        self.analysis.from_current.clicked.connect(self.goal_from_current)
        self.analysis.from_object.clicked.connect(self.goal_from_object)
        self.analysis.solve.clicked.connect(self.solve_ik)
        self.analysis.apply.clicked.connect(self.apply_ik)
        self.analysis.policy_apply.clicked.connect(self.apply_collision_policy)
        self.analysis.check_pose.clicked.connect(self.check_collision)
        self.analysis.capture_start.clicked.connect(self.capture_edge_start)
        self.analysis.check_edge.clicked.connect(self.check_edge)
        self.analysis.allow_add.clicked.connect(self.add_allowed_pair)
        self.analysis.allow_remove.clicked.connect(self.remove_allowed_pair)
        self.analysis.collision_filter.toggled.connect(self._invalidate_ik)
        for field in self.analysis.goal.fields:
            field.valueChanged.connect(self._invalidate_ik)
        self.scene.subscribe(self._analysis_scene_changed)
        self._refresh_policy()
        self.analysis.check_edge.setEnabled(False)
        help_action = self.menuBar().actions()[-1].menu().actions()[0]
        help_action.triggered.disconnect()
        help_action.triggered.connect(
            lambda: QMessageBox.information(
                self,
                "Phase 3 기구학 / 충돌 검사",
                "IK / 충돌 탭에서 World 목표 TCP, IK 후보, 현재 자세와 관절 구간을 검사합니다.\n"
                "검사 설정은 프로젝트에 저장됩니다. "
                "S922 CAD 외형 근사는 명시적으로 선택해야 합니다.\n"
                "장면 변경은 결과를 무효화합니다. 실제 장비 연결과 경로 계획은 제공하지 않습니다.",
            )
        )

    def _invalidate_ik(self, *_):
        self.ik_result = None
        self.ik_token = None
        self.analysis.apply.setEnabled(False)
        self.analysis.ik_status.setText("목표/입력 변경 · IK 재계산 필요")

    def _analysis_scene_changed(self, _):
        self._invalidate_ik()
        self.collision_report = None
        self.edge_report = None
        self._clear_overlays()
        self.analysis.pairs.clear()
        self.analysis.status.setText("장면/로봇/검사 설정 변경 · 이전 검사 결과 무효")
        self._refresh_policy()
        if self.edge_start is not None and self.edge_start[1] != self.scene.document.robot.source:
            self.edge_start = None
            self.analysis.start_status.setText("로봇 모델 변경 · 시작 자세를 다시 기억하세요.")
        self.analysis.check_edge.setEnabled(self.edge_start is not None and not self.busy)

    def _refresh_policy(self):
        doc = self.scene.document
        signature = (
            doc.collision,
            tuple((str(o.id), o.name) for o in doc.objects),
            tuple(self.model.links),
        )
        if signature == self._policy_signature:
            return
        self._policy_signature = signature
        self.analysis.margin.setValue(doc.collision.margin_m * 1000)
        self.analysis.resolution.setValue(doc.collision.edge_resolution_m * 1000)
        self.analysis.fallback.setChecked(doc.collision.use_visual_fallback)
        names = {f"link:{name}": f"로봇 · {name}" for name in self.model.links}
        names.update({f"object:{obj.id}": obj.name for obj in doc.objects})
        for combo in (self.analysis.allow_a, self.analysis.allow_b):
            previous = combo.currentData()
            combo.clear()
            for key, label in names.items():
                combo.addItem(label, key)
            if combo.findData(previous) >= 0:
                combo.setCurrentIndex(combo.findData(previous))
        self.analysis.allowed.clear()
        for pair in doc.collision.allowed_pairs:
            item = QListWidgetItem(" ↔ ".join(names.get(key, key) for key in pair))
            item.setData(Qt.ItemDataRole.UserRole, pair)
            self.analysis.allowed.addItem(item)

    def apply_collision_policy(self):
        if self.busy:
            return
        doc = self.scene.document
        values = doc.collision.model_dump() | dict(
            margin_m=self.analysis.margin.value() / 1000,
            edge_resolution_m=self.analysis.resolution.value() / 1000,
            use_visual_fallback=self.analysis.fallback.isChecked(),
        )
        policy = CollisionSettings.model_validate(values)
        self.scene.replace(doc.model_copy(update={"collision": policy}), "충돌 검사 설정 변경")

    def add_allowed_pair(self):
        if self.busy:
            return
        a, b = self.analysis.allow_a.currentData(), self.analysis.allow_b.currentData()
        if not a or not b or a == b:
            self.analysis.status.setText("서로 다른 두 대상을 선택하세요.")
            return
        doc = self.scene.document
        pair = tuple(sorted((a, b)))
        if pair in tuple(tuple(sorted(p)) for p in doc.collision.allowed_pairs):
            return
        policy = CollisionSettings.model_validate(
            doc.collision.model_dump() | {"allowed_pairs": doc.collision.allowed_pairs + (pair,)}
        )
        self.scene.replace(doc.model_copy(update={"collision": policy}), "허용 충돌 쌍 추가")

    def remove_allowed_pair(self):
        if self.busy:
            return
        item = self.analysis.allowed.currentItem()
        if item is None:
            return
        pair = tuple(item.data(Qt.ItemDataRole.UserRole))
        doc = self.scene.document
        policy = doc.collision.model_copy(
            update={"allowed_pairs": tuple(p for p in doc.collision.allowed_pairs if p != pair)}
        )
        self.scene.replace(doc.model_copy(update={"collision": policy}), "허용 충돌 쌍 삭제")

    def goal_from_current(self):
        self.analysis.goal.set_pose(matrix_pose(self.fk.tcp))

    def goal_from_object(self):
        if self.selected_id is None:
            self.analysis.ik_status.setText("목표 객체/좌표계를 선택하세요.")
            return
        matrix = self.scene.world_transforms(self.fk.tcp)[self.selected_id]
        self.analysis.goal.set_pose(matrix_pose(matrix))

    def solve_ik(self):
        if self.busy:
            return
        self._invalidate_ik()
        doc, token, model = self.scene.document, self.scene.token(), self.model
        goal = self.analysis.goal.value()
        filtered = self.analysis.collision_filter.isChecked()
        self.analysis.ik_status.setText("IK 계산 중…")

        def task():
            accept = None
            if filtered:
                checker = FCLSceneChecker(model, doc, token)
                if not checker.check(doc.robot.joints.positions).complete:
                    raise ValueError(
                        "로봇 충돌 형상이 없습니다. CAD 외형 근사를 명시적으로 적용하거나 "
                        "충돌 통과 후보 필터를 끄고 기구학만 계산하세요."
                    )

                def accept(q):
                    return checker.check(q).clear

            r = doc.robot
            return BoundedIK().solve(
                model, goal, r.joints.positions, r.tool_link, r.base, r.tool_offset, accept=accept
            )

        def ready(result):
            if not self.scene.is_current(token) or self.analysis.goal.value() != goal:
                self.append_log("변경된 입력의 IK 결과 폐기")
                return
            self.ik_result, self.ik_token = result, token
            self.analysis.apply.setEnabled(result.success)
            label = "수렴" if result.success else "해를 찾지 못함"
            reason = "충돌 필터 적용" if filtered else "충돌 미검사"
            coordinates = (
                "CAD 상대각·미보정"
                if model.provenance.joint_coordinates == "cad_relative"
                else "모델 좌표"
            )
            self.analysis.ik_status.setText(
                f"{label} · {reason}\n위치 {result.position_error_m * 1000:.4f} mm / "
                f"회전 {math.degrees(result.orientation_error_rad):.5f}°\n"
                f"rank {result.diagnostics.rank}/6 · "
                f"condition {result.diagnostics.condition:.3g} · "
                f"{'특이/부족 자유도' if result.diagnostics.singular else '정상 rank'} · "
                f"{result.evaluations} 평가 / {result.attempts} 초기값\n"
                f"{coordinates}"
            )
            self.append_log(
                f"IK {result.reason}: {result.position_error_m:.6g} m, "
                f"{result.orientation_error_rad:.6g} rad"
            )

        self._run_job(task, ready)

    def apply_ik(self):
        if self.busy or not self.ik_result or not self.ik_result.success:
            return
        if self.ik_token is None or not self.scene.is_current(self.ik_token):
            self._invalidate_ik()
            return
        robot = self.scene.document.robot
        joints = JointState(names=robot.joints.names, positions=self.ik_result.positions)
        self.scene.update_robot(robot.model_copy(update={"joints": joints}))
        self.append_log("IK 후보를 화면에 적용 · 적용 후 현재 자세 검사를 다시 실행하세요.")

    def check_collision(self):
        if self.busy:
            return
        doc, token, model = self.scene.document, self.scene.token(), self.model
        self.analysis.status.setText("현재 자세 검사 중…")

        def ready(report):
            if not self.scene.is_current(token):
                self.append_log("변경된 장면의 충돌 결과 폐기")
                return
            self.collision_report = report
            self.edge_report = None
            self._show_report(report)

        self._run_job(
            lambda: FCLSceneChecker(model, doc, token).check(doc.robot.joints.positions), ready
        )

    def capture_edge_start(self):
        if self.busy:
            return
        robot = self.scene.document.robot
        self.edge_start = (robot.joints.positions, robot.source)
        self.edge_report = None
        self.collision_report = None
        self._clear_overlays()
        self.analysis.pairs.clear()
        self.analysis.status.setText("시작 자세 기억 완료 · 구간 검사 전")
        self.analysis.start_status.setText(
            "시작 q: "
            + ", ".join(f"{v:.3f}" for v in robot.joints.positions)
            + "\n현재 Base/TCP/장면 기준으로 재검사합니다."
        )
        self.analysis.check_edge.setEnabled(not self.busy)

    def check_edge(self):
        if self.busy or self.edge_start is None:
            return
        doc, token, model = self.scene.document, self.scene.token(), self.model
        if self.edge_start[1] != doc.robot.source:
            self.edge_start = None
            return
        start = self.edge_start[0]
        self.analysis.status.setText("관절 선형 구간 검사 중…")

        def ready(report):
            if not self.scene.is_current(token):
                self.append_log("변경된 장면의 구간 결과 폐기")
                return
            self.edge_report = report
            self.collision_report = None
            if report.report is not None:
                self._show_report(report.report)
            else:
                self._clear_overlays()
                self.analysis.pairs.clear()
            location = (
                f" · 첫 위반 t={report.failure_fraction:.4f}"
                if report.failure_fraction is not None
                else ""
            )
            detail = self.analysis.status.text() if report.report is not None else ""
            self.analysis.status.setText(
                f"구간 {'통과' if report.clear else '미통과'} · {report.reason}{location}\n"
                f"샘플 {report.samples_checked}/{report.samples_required} · "
                f"이동량 상한 {report.interval_motion_bound_m * 1000:.3f} mm\n"
                f"추가 여유 포함 {report.effective_margin_m * 1000:.3f} mm\n"
                "빨간 윤곽/접점은 검사한 샘플 시점입니다.\n" + detail
            )

        self._run_job(
            lambda: FCLSceneChecker(model, doc, token).check_edge(
                start, doc.robot.joints.positions
            ),
            ready,
        )

    def _show_report(self, report):
        self.analysis.pairs.clear()
        names = {f"link:{name}": name for name in self.model.links}
        names.update({f"object:{o.id}": o.name for o in self.scene.document.objects})
        for pair in report.violations[:500]:
            label = (
                f"침투 {pair.penetration_m * 1000:.3f}"
                if pair.intersecting
                else f"{pair.distance_m * 1000:.3f}"
            )
            self.analysis.pairs.addTopLevelItem(
                QTreeWidgetItem([names.get(pair.a, pair.a), names.get(pair.b, pair.b), label])
            )
        distance = (
            f"{report.closest.distance_m * 1000:.3f} mm" if report.closest else "검사 쌍 없음"
        )
        state = (
            "검사 불완전 · 로봇 충돌 형상 누락"
            if not report.complete
            else ("충돌/여유거리 위반" if report.violations else "형상 검사 통과")
        )
        approximation = " · 근사 포함" if any("approximation" in w for w in report.warnings) else ""
        self.analysis.status.setText(
            f"{state}{approximation}\n최소 거리 {distance} · "
            f"{report.checked_pairs} part 쌍 / 제외 {len(report.excluded_pairs)} 대상 쌍\n"
            f"위반 {len(report.violations)}개 (목록 최대 500개) · 실제 장비 안전 검증 아님"
        )
        self.analysis.status.setToolTip(
            "\n".join(report.warnings) + "\n제외: " + str(report.excluded_pairs)
        )
        self._draw_report(report)
        self.statusBar().showMessage(state + approximation + " · 경로/실제 장비 미검증")
        self.append_log(self.analysis.status.text().replace("\n", " | "))

    def _draw_report(self, report):
        self._clear_overlays()
        doc = self.scene.document
        r = doc.robot
        fk = TreeKinematics().forward(
            self.model, report.positions, r.tool_link, r.base, r.tool_offset
        )
        world = SceneManager(doc).world_transforms(fk.tcp)
        owners = {owner for pair in report.violations for owner in (pair.a, pair.b)}
        for owner in owners:
            if owner.startswith("link:"):
                link = owner[5:]
                sources = [
                    actor for (name, _), actor in self.viewport.actors.items() if name == link
                ]
                matrix = fk.links[link]
            else:
                key = owner[7:]
                sources = [self.scene_view.actors[key]] if key in self.scene_view.actors else []
                matrix = world[key]
            for source in sources:
                actor = self.viewport.plotter.add_mesh(
                    source.mapper.dataset,
                    color="#ff5267",
                    style="wireframe",
                    line_width=2,
                    opacity=0.85,
                    pickable=False,
                    reset_camera=False,
                    render=False,
                )
                actor.user_matrix = matrix
                self.overlays.append(actor)
        for pair in report.violations[:20]:
            point = (np.asarray(pair.point_a) + pair.point_b) / 2
            self.overlays.append(
                self.viewport.plotter.add_mesh(
                    pv.Sphere(radius=0.008, center=point),
                    color="#ff5267",
                    pickable=False,
                    reset_camera=False,
                    render=False,
                )
            )
        if report.closest is not None and report.closest.distance_m > 1e-8:
            self.overlays.append(
                self.viewport.plotter.add_mesh(
                    pv.Line(report.closest.point_a, report.closest.point_b),
                    color="#ffce77",
                    line_width=4,
                    pickable=False,
                    reset_camera=False,
                    render=False,
                )
            )
        self.viewport.plotter.render()

    def _clear_overlays(self):
        for actor in self.overlays:
            self.viewport.plotter.remove_actor(actor, render=False)
        self.overlays.clear()
        self.viewport.plotter.render()

    def _set_busy(self, value):
        super()._set_busy(value)
        if hasattr(self, "analysis"):
            self.analysis.setEnabled(not value)
            self.analysis.apply.setEnabled(
                not value
                and self.ik_result is not None
                and self.ik_result.success
                and self.scene.is_current(self.ik_token)
            )
            self.analysis.check_edge.setEnabled(not value and self.edge_start is not None)
            if value:
                self.scene_view.clear_widget()
