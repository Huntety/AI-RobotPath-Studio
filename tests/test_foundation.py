"""Data-boundary and transform convention checks independent of Qt."""

import numpy as np
import pytest
from pydantic import ValidationError

from robotstudio_ai.core.schema import JointState, Pose
from robotstudio_ai.core.transforms import matrix_pose, pose_matrix, transform


def test_transform_convention_and_roundtrip():
    matrix = transform((1, 2, 3), (0, 0, np.pi / 2))
    np.testing.assert_allclose(matrix @ [1, 0, 0, 1], [1, 3, 3, 1], atol=1e-12)
    np.testing.assert_allclose(pose_matrix(matrix_pose(matrix)), matrix, atol=1e-12)
    np.testing.assert_allclose(np.linalg.inv(matrix) @ matrix, np.eye(4), atol=1e-12)


@pytest.mark.parametrize("quaternion", [(0, 0, 0, 0), (0, 0, 0, 2), (np.nan, 0, 0, 1)])
def test_reject_invalid_quaternions(quaternion):
    with pytest.raises(ValidationError):
        Pose(quaternion_xyzw=quaternion)


def test_reject_invalid_joint_states():
    for values in (
        {"names": ("j", "j"), "positions": (0, 0)},
        {"names": ("j",), "positions": (0, 1)},
        {"names": ("j",), "positions": (np.inf,)},
    ):
        with pytest.raises(ValidationError):
            JointState(**values)


def test_reject_non_rigid_transform():
    matrix = np.eye(4)
    matrix[0, 0] = 2
    with pytest.raises(ValueError):
        matrix_pose(matrix)


def test_pose_immutable_and_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Pose(unknown=1)
    with pytest.raises(ValidationError):
        Pose().position_m = (1, 2, 3)
