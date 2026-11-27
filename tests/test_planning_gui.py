"""Native Phase 3 UI, async stale results, persistence and collision overlays."""

import threading

import numpy as np
import pytest
from PySide6.QtWidgets import QMessageBox

from robotstudio_ai.core.inverse_kinematics import BoundedIK
from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.scene import SceneObject, SphereShape
from robotstudio_ai.core.schema import Pose
from robotstudio_ai.core.transforms import matrix_pose
from robotstudio_ai.gui.planning_workbench import PlanningWorkbench
from robotstudio_ai.settings import generic_config_path, load_settings, s922_config_path

pytestmark = pytest.mark.gui


@pytest.fixture
def planning(qtbot, tmp_path, monkeypatch):
    settings, model = load_settings(generic_config_path())
    w = PlanningWorkbench(settings, model, cache_dir=tmp_path / "cache")

    def before_close(widget):
        qtbot.waitUntil(lambda: not widget.busy, timeout=30000)
        widget.scene.mark_saved()

    qtbot.addWidget(w, before_close_func=before_close)
    w.errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: w.errors.append(args[-1]))
    w.show()
    qtbot.waitExposed(w)
    w.tabs.setCurrentIndex(3)
    yield w


def wait(qtbot, w):
    qtbot.waitUntil(lambda: not w.busy, timeout=30000)
    assert not w.errors, w.errors


def test_ik_target_apply_undo_and_input_invalidation(planning, qtbot):
    w = planning
    initial = w.scene.document.robot.joints.positions
    q = [0.2, -0.4, 0.8, 0.2, 0.4, -0.2]
    target = TreeKinematics().forward(w.model, q, w.tool_link, w.base, w.tool_offset).tcp
    w.analysis.goal.set_pose(matrix_pose(target))
    w.analysis.solve.click()
    wait(qtbot, w)
    assert w.ik_result.success and w.analysis.apply.isEnabled()
    assert "충돌 필터 적용" in w.analysis.ik_status.text()
    w.analysis.goal.fields[0].setValue(w.analysis.goal.fields[0].value() + 1)
    assert w.ik_result is None and not w.analysis.apply.isEnabled()
    w.analysis.goal.set_pose(matrix_pose(target))
    w.solve_ik()
    wait(qtbot, w)
    w.apply_ik()
    np.testing.assert_allclose(w.fk.tcp, target, atol=1e-5)
    assert w.ik_result is None
    w.scene.undo()
    np.testing.assert_allclose(w.scene.document.robot.joints.positions, initial)


def test_collision_full_link_overlay_and_revision_invalidation(planning, qtbot):
    w = planning
    w.reset_zero()
    obj = SceneObject(
        name="obstacle", shape=SphereShape(radius_m=0.02), pose=Pose(position_m=(0.16, 0, 0.3))
    )
    w.scene.add(obj)
    w.analysis.check_pose.click()
    wait(qtbot, w)
    assert w.collision_report.complete and not w.collision_report.clear
    assert any("link:link2" in (p.a, p.b) for p in w.collision_report.violations)
    assert w.overlays and w.analysis.pairs.topLevelItemCount() > 0
    token = w.collision_report.token
    w.grab().save(str(w.cache_dir.parent / "phase3-gui-contact.png"))
    w.scene.update_object(obj.model_copy(update={"pose": Pose(position_m=(2, 0, 0))}))
    assert w.collision_report is None and not w.overlays
    assert not w.scene.is_current(token) and "무효" in w.analysis.status.text()


def test_edge_remember_and_intermediate_collision(planning, qtbot):
    w = planning
    w.reset_zero()
    obj = SceneObject(
        name="thin obstacle",
        shape=SphereShape(radius_m=0.015),
        pose=Pose(position_m=(0.16, 0, 0.3)),
    )
    w.scene.add(obj)
    w.set_joint(0, -0.8)
    w.capture_edge_start()
    w.check_collision()
    wait(qtbot, w)
    assert w.collision_report.clear
    w.set_joint(0, 0.8)
    w.check_collision()
    wait(qtbot, w)
    assert w.collision_report.clear
    assert w.analysis.check_edge.isEnabled()
    w.analysis.check_edge.click()
    wait(qtbot, w)
    assert w.edge_report.complete and not w.edge_report.clear
    assert 0 < w.edge_report.failure_fraction < 1
    assert w.overlays and "샘플" in w.analysis.status.text()
    w.scene.undo()
    assert w.edge_report is None


def test_policy_allowed_pairs_project_restore_and_undo(planning, qtbot, tmp_path):
    w = planning
    obj = SceneObject(name="fixture")
    w.scene.add(obj)
    w.analysis.margin.setValue(12)
    w.analysis.resolution.setValue(6)
    w.analysis.fallback.setChecked(True)
    w.analysis.policy_apply.click()
    assert w.scene.document.collision.margin_m == 0.012
    w.analysis.allow_a.setCurrentIndex(w.analysis.allow_a.findData("link:base_link"))
    w.analysis.allow_b.setCurrentIndex(w.analysis.allow_b.findData(f"object:{obj.id}"))
    w.analysis.allow_add.click()
    expected = w.scene.document.collision
    assert len(expected.allowed_pairs) == 1
    w.scene.undo()
    assert not w.scene.document.collision.allowed_pairs
    w.scene.redo()
    assert w.scene.document.collision == expected
    project = tmp_path / "project.rsai"
    w.save_project_path(project)
    wait(qtbot, w)
    w.analysis.margin.setValue(2)
    w.apply_collision_policy()
    w.load_project_path(project)
    wait(qtbot, w)
    assert w.scene.document.collision == expected
    assert w.analysis.margin.value() == 12 and w.analysis.allowed.count() == 1


def test_stale_worker_result_is_discarded(planning, qtbot, monkeypatch):
    w = planning
    w.analysis.collision_filter.setChecked(False)
    w.goal_from_current()
    original = BoundedIK.solve
    started, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(BoundedIK, "solve", delayed)
    w.solve_ik()
    try:
        qtbot.waitUntil(started.is_set, timeout=5000)
        assert w.busy and not w.analysis.isEnabled()
        w.scene.add(SceneObject(name="changed while calculating"))
    finally:
        release.set()
    wait(qtbot, w)
    assert w.ik_result is None and not w.analysis.apply.isEnabled()
    assert "결과 폐기" in w.log.toPlainText()


def test_selected_object_target_uses_world_parent_transform(planning):
    w = planning
    parent = SceneObject(name="parent", pose=Pose(position_m=(0.3, 0.2, 0.1)))
    child = SceneObject(
        name="target", parent_frame=str(parent.id), pose=Pose(position_m=(0.1, 0, 0.2))
    )
    w.scene.add(parent)
    w.scene.add(child)
    w.select_item(str(child.id))
    w.analysis.from_object.click()
    np.testing.assert_allclose(w.analysis.goal.value().position_m, (0.4, 0.2, 0.3))


@pytest.mark.cad_assets
def test_s922_default_incomplete_then_explicit_approximation(qtbot, tmp_path, monkeypatch):
    if not s922_config_path().is_file():
        pytest.skip("Local vendor CAD is not redistributed")
    settings, model = load_settings(s922_config_path())
    w = PlanningWorkbench(settings, model, cache_dir=tmp_path / "cache")
    qtbot.addWidget(w, before_close_func=lambda widget: widget.scene.mark_saved())
    w.errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: w.errors.append(args[-1]))
    w.show()
    qtbot.waitExposed(w)
    w.check_collision()
    wait(qtbot, w)
    assert not w.collision_report.complete and "불완전" in w.analysis.status.text()
    w.analysis.fallback.setChecked(True)
    w.apply_collision_policy()
    w.check_collision()
    wait(qtbot, w)
    assert w.collision_report.complete and "근사" in w.analysis.status.text()
    w.tabs.setCurrentIndex(3)
    w.grab().save(str(tmp_path / "phase3-s922.png"))
