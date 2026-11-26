"""Analytic Jacobian vs independent differences, bounded IK and failure contracts."""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from robotstudio_ai.core.inverse_kinematics import (
    BoundedIK,
    IKOptions,
    diagnose_jacobian,
    pose_residual,
    residual_jacobian,
)
from robotstudio_ai.core.kinematics import IDENTITY_POSE, TreeKinematics
from robotstudio_ai.core.schema import Pose
from robotstudio_ai.core.transforms import matrix_pose
from robotstudio_ai.core.urdf import load_urdf
from robotstudio_ai.settings import generic_config_path, load_settings, s922_config_path


@pytest.fixture
def model():
    return load_settings(generic_config_path())[1]


def numerical_jacobian(model, q, link, base=IDENTITY_POSE, offset=IDENTITY_POSE):
    solver = TreeKinematics()
    columns, epsilon = [], 1e-6
    for i in range(len(q)):
        delta = np.eye(len(q))[i] * epsilon
        plus = solver.forward(model, np.asarray(q) + delta, link, base, offset).tcp
        minus = solver.forward(model, np.asarray(q) - delta, link, base, offset).tcp
        columns.append(
            np.r_[
                (plus[:3, 3] - minus[:3, 3]) / (2 * epsilon),
                Rotation.from_matrix(plus[:3, :3] @ minus[:3, :3].T).as_rotvec() / (2 * epsilon),
            ]
        )
    return np.array(columns).T


def test_geometric_jacobian_random_poses_base_and_offset(model):
    solver = TreeKinematics()
    base = Pose(
        position_m=(1, -2, 0.3),
        quaternion_xyzw=tuple(Rotation.from_euler("xyz", [0.4, -0.2, 0.9]).as_quat()),
    )
    offset = Pose(
        position_m=(0.08, -0.04, 0.12),
        quaternion_xyzw=tuple(Rotation.from_euler("xyz", [0.3, 0.5, -0.7]).as_quat()),
    )
    for q in np.random.default_rng(923).uniform(-1.2, 1.2, (20, 6)):
        actual = solver.jacobian(model, q, "tool0", base, offset)
        np.testing.assert_allclose(
            actual, numerical_jacobian(model, q, "tool0", base, offset), atol=7e-10
        )
        assert not actual.flags.writeable


def test_rotation_log_derivative_large_orientation_error(model):
    solver = TreeKinematics()
    q = np.array([0.3, -0.8, 0.9, 0.4, -0.5, 0.7])
    target = solver.forward(model, [-1, 0.6, -0.8, 1, 0.6, -0.7], "tool0").tcp
    actual = solver.forward(model, q, "tool0").tcp
    residual = pose_residual(target, actual)
    jac = residual_jacobian(residual, solver.jacobian(model, q, "tool0"))
    columns = []
    for delta in np.eye(6) * 1e-6:
        columns.append(
            (
                pose_residual(target, solver.forward(model, q + delta, "tool0").tcp)
                - pose_residual(target, solver.forward(model, q - delta, "tool0").tcp)
            )
            / 2e-6
        )
    np.testing.assert_allclose(jac, np.array(columns).T, atol=1e-9)


def test_prismatic_fixed_and_unrelated_branch(tmp_path):
    path = tmp_path / "tree.urdf"
    path.write_text("""<robot name="tree"><link name="root"/><link name="a"/>
      <link name="tool"/><link name="branch"/>
      <joint name="slide" type="prismatic"><parent link="root"/><child link="a"/>
       <origin rpy="0 0 1.5707963267948966"/><axis xyz="1 0 0"/>
       <limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
      <joint name="fixed" type="fixed"><parent link="a"/><child link="tool"/>
       <origin xyz="0 0 .1"/></joint>
      <joint name="spin" type="continuous"><parent link="root"/><child link="branch"/>
       <axis xyz="0 0 1"/><limit effort="1" velocity="1"/></joint></robot>""")
    robot = load_urdf(path)
    q = [0.1 if j.name == "slide" else 0.2 for j in robot.active_joints]
    jac = TreeKinematics().jacobian(robot, q, "tool")
    np.testing.assert_allclose(jac, numerical_jacobian(robot, q, "tool"), atol=1e-10)
    np.testing.assert_allclose(jac[:, [j.name for j in robot.active_joints].index("spin")], 0)
    target = matrix_pose(TreeKinematics().forward(robot, q, "tool").tcp)
    result = BoundedIK().solve(robot, target, [0, 0], "tool")
    assert result.success


def test_ik_random_reachable_full_pose_and_base_tool(model):
    solver = TreeKinematics()
    base = Pose(
        position_m=(0.3, -0.4, 0.6), quaternion_xyzw=tuple(Rotation.from_euler("z", 0.8).as_quat())
    )
    offset = Pose(position_m=(0.04, 0.03, 0.12))
    for q in np.random.default_rng(924).uniform(-1, 1, (15, 6)):
        target = matrix_pose(solver.forward(model, q, "tool0", base, offset).tcp)
        result = BoundedIK().solve(
            model, target, np.clip(q + 0.15, -1.5, 1.5), "tool0", base, offset
        )
        assert result.success, result
        model.validate_positions(result.positions)
        assert result.position_error_m <= 1e-5 and result.orientation_error_rad <= 1e-4


def test_ik_handles_singular_start_pi_rotation_and_limits(model):
    solver = TreeKinematics()
    for q in (
        [np.pi, 0, 0, 0, 0, 0],
        [0.4, -0.8, 1.3, 0.7, -0.6, 0.2],
        [-np.pi, 0.5, -1, 0.2, 0.4, -0.2],
    ):
        target = matrix_pose(solver.forward(model, q, "tool0").tcp)
        result = BoundedIK().solve(model, target, [0] * 6, "tool0")
        assert result.success, result
    assert diagnose_jacobian(solver.jacobian(model, [0] * 6, "tool0")).singular
    diag = diagnose_jacobian(solver.jacobian(model, [0.3, -0.8, 1.2, 0.3, 0.4, -0.2], "tool0"))
    assert diag.rank == 6 and not diag.singular and np.isfinite(diag.condition)


def test_ik_failure_is_not_reported_as_unreachable_and_filter_is_respected(model):
    result = BoundedIK().solve(
        model,
        Pose(position_m=(10, 0, 0)),
        [0] * 6,
        "tool0",
        options=IKOptions(attempts=2, max_evaluations=20),
    )
    assert not result.success and result.reason == "no_solution_found"
    target = matrix_pose(TreeKinematics().forward(model, [0] * 6, "tool0").tcp)
    result = BoundedIK().solve(
        model, target, [0] * 6, "tool0", options=IKOptions(attempts=2), accept=lambda q: False
    )
    assert not result.success and result.reason == "candidates_rejected"
    with pytest.raises(ValueError):
        BoundedIK().solve(model, target, [100] * 6, "tool0")


@pytest.mark.cad_assets
def test_s922_cad_relative_jacobian_and_ik():
    if not s922_config_path().is_file():
        pytest.skip("Local vendor CAD is not redistributed")
    settings, robot = load_settings(s922_config_path())
    q = np.array([0.2, -0.3, 0.4, 0.2, -0.4, 0.3])
    solver = TreeKinematics()
    np.testing.assert_allclose(
        solver.jacobian(robot, q, settings.robot.tool_link),
        numerical_jacobian(robot, q, settings.robot.tool_link),
        atol=1e-9,
    )
    result = BoundedIK().solve(
        robot,
        matrix_pose(solver.forward(robot, q, settings.robot.tool_link).tcp),
        q + 0.1,
        settings.robot.tool_link,
    )
    assert result.success
    assert robot.provenance.joint_coordinates == "cad_relative"
