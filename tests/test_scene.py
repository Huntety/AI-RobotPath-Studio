"""Atomic scene edits, hierarchy transforms, history isolation and invalidation."""

from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.spatial.transform import Rotation

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


@pytest.fixture
def scene():
    robot = SceneRobot(
        source=RobotSource(kind="builtin", model_id="generic_6axis_v1"),
        joints=JointState(names=("j1",), positions=(0,)),
        tool_link="tool0",
    )
    return SceneManager(SceneDocument(robot=robot))


def test_edit_undo_redo_revision_never_revalidates_old_token(scene):
    initial = scene.token()
    obj = SceneObject(name="box")
    scene.add(obj)
    assert scene.dirty and scene.can_undo and not scene.is_current(initial)
    first = scene.token()
    scene.update_object(obj.model_copy(update={"pose": Pose(position_m=(1, 2, 3))}))
    scene.undo()
    assert scene.get_object(obj.id).pose == obj.pose
    assert not scene.is_current(first)
    scene.redo()
    assert scene.get_object(obj.id).pose.position_m == (1, 2, 3)
    scene.mark_saved()
    assert not scene.dirty
    scene.undo()
    assert scene.dirty
    scene.redo()
    assert not scene.dirty


def test_invalid_edit_is_atomic_and_preserves_history(scene):
    obj = SceneObject(name="A")
    scene.add(obj)
    before, token = scene.document, scene.token()
    with pytest.raises(ValueError):
        scene.add(SceneObject(name="a"))
    assert scene.document == before and scene.is_current(token)
    with pytest.raises(ValueError):
        scene.update_object(obj.model_copy(update={"mass_kg": -1}))
    assert scene.document == before
    scene.undo()
    assert not scene.document.objects


def test_graph_cycles_dangling_and_duplicate_ids_rejected(scene):
    a = SceneObject(name="parent")
    b = SceneObject(name="child", parent_frame=str(a.id))
    scene.add(a)
    scene.add(b)
    with pytest.raises(ValueError):
        scene.update_object(a.model_copy(update={"parent_frame": str(b.id)}))
    with pytest.raises(ValueError):
        scene.update_object(b.model_copy(update={"parent_frame": str(uuid4())}))
    with pytest.raises(ValueError):
        scene.add(a.model_copy(update={"name": "another"}))
    assert len(scene.document.objects) == 2


def test_parent_composition_and_reparent_preserves_world(scene):
    parent = SceneObject(
        name="frame",
        shape=FrameShape(),
        pose=Pose(
            position_m=(1, 2, 0),
            quaternion_xyzw=tuple(Rotation.from_euler("z", 90, degrees=True).as_quat()),
        ),
    )
    child = SceneObject(name="child", pose=Pose(position_m=(1, 0, 0)), parent_frame=str(parent.id))
    scene.add(parent)
    scene.add(child)
    original = scene.world_transforms()[str(child.id)]
    np.testing.assert_allclose(original[:3, 3], [1, 3, 0], atol=1e-12)
    scene.reparent(child.id, "world")
    np.testing.assert_allclose(scene.world_transforms()[str(child.id)], original, atol=1e-12)
    scene.undo()
    assert scene.get_object(child.id).parent_frame == str(parent.id)


def test_base_and_tool_parent_frames(scene):
    robot = scene.document.robot.model_copy(update={"base": Pose(position_m=(0.5, 0, 0))})
    scene.update_robot(robot)
    a = SceneObject(name="base child", parent_frame="robot_base", pose=Pose(position_m=(1, 0, 0)))
    b = SceneObject(name="tool child", parent_frame="robot_tool")
    scene.add(a)
    scene.add(b)
    with pytest.raises(ValueError, match="Tool FK"):
        scene.world_transforms()
    tool = np.eye(4)
    tool[:3, 3] = (0, 2, 3)
    transforms = scene.world_transforms(tool)
    np.testing.assert_allclose(transforms[str(a.id)][:3, 3], [1.5, 0, 0])
    np.testing.assert_allclose(transforms[str(b.id)][:3, 3], [0, 2, 3])


def test_duplicate_delete_subtree_as_single_reversible_edit(scene):
    parent = SceneObject(name="parent", properties={"nested": {"value": 1}})
    child = SceneObject(name="child", parent_frame=str(parent.id))
    scene.add(parent)
    scene.add(child)
    clone_id = scene.duplicate(child.id)
    assert clone_id != child.id
    assert scene.get_object(clone_id).parent_frame == str(parent.id)
    scene.remove(parent.id)
    assert not scene.document.objects
    scene.undo()
    assert len(scene.document.objects) == 3
    leaked = scene.document
    leaked.objects[0].properties["nested"]["value"] = 999
    assert scene.get_object(parent.id).properties["nested"]["value"] == 1


def test_gesture_coalescing_and_redo_branching(scene):
    obj = SceneObject(name="box")
    scene.add(obj)
    for x in (1, 2, 3):
        scene.update_object(
            obj.model_copy(update={"pose": Pose(position_m=(x, 0, 0))}), key="drag-1"
        )
    assert scene.revision == 4
    scene.end_gesture()
    scene.undo()
    assert scene.get_object(obj.id).pose.position_m == (0, 0, 0)
    scene.redo()
    assert scene.get_object(obj.id).pose.position_m == (3, 0, 0)
    scene.undo()
    scene.update_object(obj.model_copy(update={"visible": False}))
    assert not scene.can_redo


def test_reset_rebind_and_bounded_history(scene):
    scene.history_limit = 2
    for i in range(4):
        scene.add(SceneObject(name=str(i)))
    scene.undo()
    scene.undo()
    scene.undo()
    assert len(scene.document.objects) == 2
    token = scene.token()
    scene.reset(scene.document)
    assert not scene.dirty and not scene.can_undo and not scene.is_current(token)
    scene.add(SceneObject(name="after reset"))
    scene.update_robot(
        scene.document.robot.model_copy(update={"visible": False}), reset_history=True
    )
    assert not scene.can_undo


@pytest.mark.parametrize(
    "shape",
    [
        lambda: BoxShape(size_m=(0, 1, 1)),
        lambda: CylinderShape(radius_m=-1),
        lambda: SphereShape(radius_m=float("nan")),
        lambda: MeshShape(asset_id="a" * 64, scale=(1, -1, 1)),
        lambda: FrameShape(size_m=0),
    ],
)
def test_invalid_shapes(shape):
    with pytest.raises(ValidationError):
        shape()


def test_mesh_reference_and_robot_source_contract(scene):
    with pytest.raises(ValueError):
        scene.add(SceneObject(name="missing", shape=MeshShape(asset_id="a" * 64)))
    with pytest.raises(ValueError):
        RobotSource(kind="urdf", model_id="x")
    with pytest.raises(ValueError):
        RobotSource(kind="builtin", model_id="x", path="secret")


def test_nonfinite_custom_metadata_and_changed_model_invalidate(scene):
    with pytest.raises(ValueError):
        SceneObject(name="bad", properties={"nested": [float("nan")]})
    token = scene.token()
    source = scene.document.robot.source.model_copy(update={"fingerprint": "a" * 64})
    scene.update_robot(scene.document.robot.model_copy(update={"source": source}))
    assert not scene.is_current(token)


def test_listener_failure_does_not_roll_back_committed_edit(scene):
    def failed(_):
        raise RuntimeError("deliberate observer failure")

    scene.subscribe(failed)
    scene.add(SceneObject(name="recorded"))
    assert len(scene.document.objects) == 1 and scene.revision == 1
