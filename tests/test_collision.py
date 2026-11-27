"""Real FCL solids, containment, model coverage, attachments and swept joint edges."""

import numpy as np
import pytest
import trimesh

from robotstudio_ai.core.collision import FCLSceneChecker
from robotstudio_ai.core.collision_settings import CollisionSettings
from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.project_io import SceneProject, import_mesh, load_project, save_project
from robotstudio_ai.core.scene import (
    BoxShape,
    MeshShape,
    RobotSource,
    SceneDocument,
    SceneManager,
    SceneObject,
    SceneRobot,
    SphereShape,
)
from robotstudio_ai.core.schema import JointState, Pose
from robotstudio_ai.core.urdf import load_urdf
from robotstudio_ai.settings import generic_config_path, load_settings, s922_config_path

DEFAULT_COLLISION = CollisionSettings()


def document(model, objects=(), assets=(), collision=DEFAULT_COLLISION):
    return SceneDocument(
        robot=SceneRobot(
            source=RobotSource(kind="builtin", model_id=model.provenance.model_id),
            joints=JointState(
                names=tuple(j.name for j in model.active_joints),
                positions=tuple(0 for _ in model.active_joints),
            ),
            tool_link="tool0",
        ),
        objects=tuple(objects),
        assets=tuple(assets),
        collision=collision,
    )


@pytest.fixture
def slider(tmp_path):
    path = tmp_path / "slider.urdf"
    path.write_text("""<robot name="slider"><link name="root"/><link name="body">
      <visual><geometry><sphere radius=".05"/></geometry></visual>
      <collision><geometry><sphere radius=".05"/></geometry></collision></link><link name="tool0"/>
      <joint name="slide" type="prismatic">
       <parent link="root"/><child link="body"/>
       <axis xyz="1 0 0"/><limit lower="-2" upper="2" effort="1" velocity="1"/></joint>
      <joint name="fixed" type="fixed"><parent link="body"/>
       <child link="tool0"/></joint></robot>""")
    return load_urdf(path)


def checker(model, doc):
    return FCLSceneChecker(model, doc, SceneManager(doc).token())


def test_analytic_spheres_distance_margin_contacts_and_hidden_geometry(slider):
    obj = SceneObject(
        name="sphere",
        shape=SphereShape(radius_m=0.05),
        pose=Pose(position_m=(0.3, 0, 0)),
        visible=False,
    )
    engine = checker(slider, document(slider, [obj]))
    result = engine.check([0])
    assert result.clear and result.checked_pairs == 1
    assert result.closest.distance_m == pytest.approx(0.2, abs=1e-9)
    np.testing.assert_allclose(result.closest.point_a, [0.05, 0, 0], atol=1e-9)
    assert not engine.check([0.195]).clear  # within 5mm margin, including equality
    contact = engine.check([0.25])
    assert not contact.clear and contact.violations[0].intersecting
    assert contact.violations[0].penetration_m > 0
    with pytest.raises(ValueError):
        engine.check([3])
    with pytest.raises(ValueError):
        engine.check([0], margin_m=np.nan)


def test_disabled_collision_and_allowed_pairs_persist_prune_and_undo(slider, tmp_path):
    obj = SceneObject(name="obstacle", shape=SphereShape(radius_m=0.2), collision_enabled=False)
    doc = document(slider, [obj])
    assert checker(slider, doc).check([0]).clear
    obj = obj.model_copy(update={"collision_enabled": True})
    pair = ("link:body", f"object:{obj.id}")
    doc = document(slider, [obj], collision=CollisionSettings(allowed_pairs=(pair,)))
    assert checker(slider, doc).check([0]).clear
    path = tmp_path / "scene.rsai"
    save_project(path, SceneProject(scene=doc))
    restored = load_project(path, tmp_path / "cache").scene
    assert restored.collision == doc.collision
    manager = SceneManager(restored)
    manager.remove(obj.id)
    assert not manager.document.collision.allowed_pairs
    manager.undo()
    assert manager.document.collision.allowed_pairs == (pair,)
    bad = doc.model_copy(
        update={"collision": CollisionSettings(allowed_pairs=(("link:nope", pair[1]),))}
    )
    with pytest.raises(ValueError, match="Unknown allowed"):
        checker(slider, bad)
    with pytest.raises(ValueError):
        CollisionSettings(allowed_pairs=(pair, pair[::-1]))


def test_tool_attached_object_uses_same_fk_and_checks_environment(slider):
    carried = SceneObject(
        name="gripper",
        shape=SphereShape(radius_m=0.05),
        parent_frame="robot_tool",
        pose=Pose(position_m=(0.2, 0, 0)),
    )
    obstacle = SceneObject(
        name="wall", shape=BoxShape(size_m=(0.04, 0.3, 0.3)), pose=Pose(position_m=(0.5, 0, 0))
    )
    doc = document(slider, [carried, obstacle])
    engine = checker(slider, doc)
    assert engine.check([0]).clear
    report = engine.check([0.3])
    assert not report.clear
    assert any(
        f"object:{carried.id}" in (p.a, p.b) and f"object:{obstacle.id}" in (p.a, p.b)
        for p in report.violations
    )
    assert ("link:body", f"object:{carried.id}") in report.excluded_pairs


def test_mid_edge_hit_and_clear_edge_with_motion_envelope(slider):
    thin = SceneObject(name="thin obstacle", shape=BoxShape(size_m=(0.002, 0.2, 0.2)))
    engine = checker(slider, document(slider, [thin]))
    assert engine.check([-0.3]).clear and engine.check([0.3]).clear
    edge = engine.check_edge([-0.3], [0.3])
    assert not edge.clear and edge.complete and 0 < edge.failure_fraction < 1
    assert edge.samples_checked > 1
    assert edge.effective_margin_m > engine.policy.margin_m
    assert edge.interval_motion_bound_m <= engine.policy.edge_resolution_m + 1e-12
    clear = engine.check_edge([-0.8], [-0.5])
    assert clear.clear and clear.complete
    limited = document(slider, [thin], collision=CollisionSettings(edge_max_samples=2))
    failure = checker(slider, limited).check_edge([-0.3], [0.3])
    assert not failure.clear and not failure.complete and failure.reason == "sample_budget_exceeded"


def test_conservative_mesh_hull_detects_containment_and_verifies_asset(slider, tmp_path):
    path = tmp_path / "box.stl"
    trimesh.creation.box(extents=(0.4, 0.4, 0.4)).export(path)
    asset, centre = import_mesh(path, tmp_path / "cache", units="m")
    obj = SceneObject(
        name="mesh container", shape=MeshShape(asset_id=asset.id), pose=Pose(position_m=centre)
    )
    doc = document(slider, [obj], [asset])
    report = checker(slider, doc).check([0])
    assert not report.clear and report.violations[0].intersecting
    assert any("Conservative mesh" in warning for warning in report.warnings)
    from pathlib import Path

    Path(asset.path).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        checker(slider, doc)


def test_self_collision_nonadjacent_links_and_joint_adjacent_exclusions():
    _, model = load_settings(generic_config_path())
    doc = document(model)
    engine = checker(model, doc)
    assert engine.check([0] * 6).clear
    report = engine.check([0, 0, 2.5, 0, 0, 0])
    assert any(p.a.startswith("link:") and p.b.startswith("link:") for p in report.violations)
    assert ("link:link2", "link:link3") in report.excluded_pairs


def test_model_identity_and_token_mismatch_rejected(slider):
    doc = document(slider)
    other = document(slider)
    with pytest.raises(ValueError, match="token"):
        FCLSceneChecker(slider, doc, SceneManager(other).token())
    wrong = doc.model_copy(
        update={
            "robot": doc.robot.model_copy(
                update={"source": RobotSource(kind="builtin", model_id="wrong")}
            )
        }
    )
    with pytest.raises(ValueError, match="identity"):
        checker(slider, wrong)


def test_rotated_base_distance_matches_independent_sphere_formula(slider):
    obj = SceneObject(
        name="sphere", shape=SphereShape(radius_m=0.1), pose=Pose(position_m=(0.6, 0.7, 0))
    )
    doc = document(slider, [obj])
    base = Pose(position_m=(0.2, 0.3, 0), quaternion_xyzw=(0, 0, np.sqrt(0.5), np.sqrt(0.5)))
    doc = doc.model_copy(update={"robot": doc.robot.model_copy(update={"base": base})})
    engine = checker(slider, doc)
    for q in np.linspace(-0.5, 0.5, 15):
        report = engine.check([q])
        expected = np.linalg.norm(np.array([0.2, 0.3 + q, 0]) - np.array([0.6, 0.7, 0])) - 0.15
        assert report.closest.distance_m == pytest.approx(expected, abs=1e-9)


def test_full_link_obstacle_and_rotational_edge():
    _, model = load_settings(generic_config_path())
    obstacle = SceneObject(
        name="link obstacle", shape=SphereShape(radius_m=0.02), pose=Pose(position_m=(0.16, 0, 0.3))
    )
    report = checker(model, document(model, [obstacle])).check([0] * 6)
    assert any("link:link2" in (p.a, p.b) for p in report.violations)
    assert (
        np.linalg.norm(
            TreeKinematics().forward(model, [0] * 6, "tool0").tcp[:3, 3]
            - np.array(obstacle.pose.position_m)
        )
        > 0.5
    )
    doc = document(model)
    edge = checker(model, doc).check_edge([0] * 6, [0.01, 0, 0, 0, 0, 0])
    assert edge.clear and edge.samples_checked >= 2
    assert edge.interval_motion_bound_m <= doc.collision.edge_resolution_m + 1e-12


@pytest.mark.cad_assets
def test_s922_missing_collision_is_not_clear_and_explicit_visual_preview():
    if not s922_config_path().is_file():
        pytest.skip("Local vendor CAD is not redistributed")
    _, model = load_settings(s922_config_path())
    doc = document(model)
    incomplete = checker(model, doc).check([0] * 6)
    assert not incomplete.clear and not incomplete.complete
    doc = doc.model_copy(update={"collision": CollisionSettings(use_visual_fallback=True)})
    engine = checker(model, doc)
    report = engine.check([0] * 6)
    assert report.complete and report.checked_pairs > 0
    assert any("Uncalibrated" in w for w in report.warnings)
    assert any("approximation" in w for w in report.warnings)
    fk = TreeKinematics().forward(model, [0] * 6, "tool0")
    for part in engine.parts:
        np.testing.assert_allclose(
            part.body.getTranslation(), (fk.links[part.frame] @ part.local)[:3, 3], atol=1e-10
        )
