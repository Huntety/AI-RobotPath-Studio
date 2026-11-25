"""URDF parsing and FK against analytic poses and matrix-exponential reference."""

from pathlib import Path

import numpy as np
import pytest
from scipy.linalg import expm

from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.schema import JointState, Pose
from robotstudio_ai.core.transforms import pose_matrix, transform
from robotstudio_ai.core.urdf import load_urdf
from robotstudio_ai.settings import load_settings


@pytest.fixture
def generic():
    return load_settings()[1]


@pytest.mark.parametrize(
    "joint,angle,xyz",
    [
        (0, 0, [0.85, 0, 0.30]),
        (0, np.pi / 2, [0, 0.85, 0.30]),
        (1, np.pi / 2, [0, 0, -0.55]),
        (2, np.pi / 2, [0.32, 0, -0.23]),
    ],
)
def test_analytic_tcp(generic, joint, angle, xyz):
    q = np.zeros(6)
    q[joint] = angle
    result = TreeKinematics().forward(generic, q, "tool0")
    np.testing.assert_allclose(result.tcp[:3, 3], xyz, atol=1e-12)
    np.testing.assert_allclose(result.links["flange"], result.tcp, atol=1e-12)


def reference_fk(q):
    """Independent hand-authored chain with expm of skew generators, not URDF data."""
    origins = [(0, 0, 0.18), (0, 0, 0.12), (0.32, 0, 0), (0.28, 0, 0), (0.09, 0, 0), (0.09, 0, 0)]
    axes = [(0, 0, 1), (0, 1, 0), (0, 1, 0), (1, 0, 0), (0, 1, 0), (1, 0, 0)]
    result = np.eye(4)
    for xyz, (x, y, z), value in zip(origins, axes, q, strict=True):
        translation = np.eye(4)
        translation[:3, 3] = xyz
        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], dtype=float)
        motion = np.eye(4)
        motion[:3, :3] = expm(skew * value)
        result = result @ translation @ motion
    flange = np.eye(4)
    flange[0, 3] = 0.07
    return result @ flange


def test_random_fk_against_independent_reference(generic):
    rng = np.random.default_rng(922)
    for q in rng.uniform(-1.5, 1.5, size=(100, 6)):
        actual = TreeKinematics().forward(generic, q, "tool0").tcp
        np.testing.assert_allclose(actual, reference_fk(q), atol=2e-12, rtol=0)


def test_world_base_and_rotated_tool(generic):
    base = Pose(position_m=(1, -2, 3), quaternion_xyzw=(0, 0, np.sqrt(0.5), np.sqrt(0.5)))
    offset = Pose(position_m=(0.1, 0.02, -0.03), quaternion_xyzw=(1, 0, 0, 0))
    q = [0.2, -0.7, 1.1, 0.3, -0.4, 0.7]
    result = TreeKinematics().forward(generic, q, "tool0", base, offset)
    expected = pose_matrix(base) @ reference_fk(q) @ pose_matrix(offset)
    np.testing.assert_allclose(result.tcp, expected, atol=2e-12)
    assert not result.tcp.flags.writeable


@pytest.mark.parametrize("q", [[0] * 5, [0] * 7, [np.nan] * 6, [np.inf] * 6, [4] * 6])
def test_reject_invalid_joint_vectors(generic, q):
    with pytest.raises(ValueError):
        TreeKinematics().forward(generic, q, "tool0")


def test_limits_and_named_state(generic):
    q = [j.lower for j in generic.active_joints]
    solver = TreeKinematics()
    solver.forward(generic, q, "tool0")
    q = [j.upper for j in generic.active_joints]
    state = JointState(names=tuple(j.name for j in generic.active_joints), positions=tuple(q))
    np.testing.assert_allclose(
        solver.forward_state(generic, state, "tool0").tcp, solver.forward(generic, q, "tool0").tcp
    )
    with pytest.raises(ValueError):
        solver.forward_state(
            generic, JointState(names=state.names[::-1], positions=state.positions), "tool0"
        )
    with pytest.raises(ValueError):
        solver.forward(generic, q, "missing")


def write_urdf(tmp_path: Path, content: str):
    path = tmp_path / "robot.urdf"
    path.write_text(content, encoding="utf-8")
    return path


def test_fixed_origin_branch_and_prismatic(tmp_path):
    path = write_urdf(
        tmp_path,
        """<robot name="test">
      <link name="a"/><link name="b"/><link name="c"/><link name="d"/>
      <joint name="slide" type="prismatic"><parent link="b"/><child link="c"/>
        <axis xyz="0 0 2"/><limit lower="-1" upper="1" velocity="1" effort="1"/></joint>
      <joint name="branch" type="fixed"><parent link="a"/><child link="d"/>
        <origin xyz="0 2 0"/></joint>
      <joint name="fixed" type="fixed"><parent link="a"/><child link="b"/>
        <origin xyz="1 0 0" rpy="0 1.5707963267948966 0"/></joint>
    </robot>""",
    )
    model = load_urdf(path)
    result = TreeKinematics().forward(model, [0.4], "c")
    np.testing.assert_allclose(result.tcp[:3, 3], [1.4, 0, 0], atol=1e-12)
    np.testing.assert_allclose(result.links["d"][:3, 3], [0, 2, 0])
    assert model.provenance.hardware_validated is False


def test_continuous_joint(tmp_path):
    path = write_urdf(
        tmp_path,
        """<robot name="continuous"><link name="a"/><link name="b"/>
      <joint name="j" type="continuous"><parent link="a"/><child link="b"/>
      <axis xyz="0 0 1"/><limit velocity="1" effort="1"/></joint></robot>""",
    )
    result = TreeKinematics().forward(load_urdf(path), [10 * np.pi], "b")
    np.testing.assert_allclose(result.tcp, np.eye(4), atol=1e-12)


@pytest.mark.parametrize(
    "content",
    [
        '<robot name="x"><link name="a"/><link name="a"/></robot>',
        '<robot name="x"><link name="a"/><link name="b"/></robot>',
        '<robot name="x"><link name="a"/><joint name="j" type="fixed">'
        '<parent link="a"/><child link="a"/></joint></robot>',
        '<robot name="x"><link name="a"/><link name="b"/><joint name="j" type="floating">'
        '<parent link="a"/><child link="b"/></joint></robot>',
        '<robot name="x"><link name="a"><visual><geometry><box size="-1 1 1"/>'
        "</geometry></visual></link></robot>",
        '<!DOCTYPE robot [<!ENTITY test "x">]><robot name="&test;"><link name="a"/></robot>',
        "<robot>",
    ],
)
def test_reject_invalid_urdf(tmp_path, content):
    with pytest.raises(ValueError):
        load_urdf(write_urdf(tmp_path, content))


@pytest.mark.parametrize(
    "joint_attrs",
    [
        '<axis xyz="0 0 0"/><limit lower="-1" upper="1" velocity="1" effort="1"/>',
        '<axis xyz="0 0 1"/>',
        '<limit lower="1" upper="-1" velocity="1" effort="1"/>',
        '<limit lower="-1" upper="1" velocity="nan" effort="1"/>',
        '<limit lower="-1" upper="1" velocity="1" effort="1"/><mimic joint="other"/>',
    ],
)
def test_invalid_joint_parameters(tmp_path, joint_attrs):
    content = (
        '<robot name="x"><link name="a"/><link name="b"/>'
        '<joint name="j" type="revolute"><parent link="a"/><child link="b"/>'
        f"{joint_attrs}</joint></robot>"
    )
    with pytest.raises(ValueError):
        load_urdf(write_urdf(tmp_path, content))


def test_visual_and_collision_origins_are_separate(generic):
    link = generic.links["link4"]
    assert link.visuals[0].kind == "cylinder"
    assert link.collisions[0].kind == "box"
    np.testing.assert_allclose(
        link.visuals[0].origin, transform((0.045, 0, 0), (0, np.pi / 2, 0)), atol=1e-12
    )


def test_relative_mesh_and_explicit_package_path(tmp_path):
    mesh = tmp_path / "part.stl"
    mesh.write_text("solid part\nendsolid part", encoding="utf-8")
    content = (
        '<robot name="mesh"><link name="base"><visual><geometry>'
        '<mesh filename="part.stl" scale="0.001 0.001 0.001"/>'
        "</geometry></visual></link></robot>"
    )
    path = write_urdf(tmp_path, content)
    assert load_urdf(path).links["base"].visuals[0].mesh_path == mesh
    path.write_text(content.replace("part.stl", "package://test/part.stl"), encoding="utf-8")
    with pytest.raises(ValueError, match="package directory"):
        load_urdf(path)
    assert load_urdf(path, package_dirs={"test": tmp_path}).links["base"].visuals[0].size == (
        0.001,
        0.001,
        0.001,
    )
