"""Right-handed active transforms acting on homogeneous column vectors."""

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from robotstudio_ai.core.schema import Pose

Matrix = NDArray[np.float64]


def transform(xyz: tuple[float, ...], rpy: tuple[float, ...]) -> Matrix:
    """URDF origin: T(xyz) @ Rz(yaw) @ Ry(pitch) @ Rx(roll), SI units."""
    if len(xyz) != 3 or len(rpy) != 3 or not np.isfinite([xyz, rpy]).all():
        raise ValueError("Origin requires finite xyz and rpy triples")
    result = np.eye(4)
    result[:3, :3] = Rotation.from_euler("xyz", rpy).as_matrix()
    result[:3, 3] = xyz
    return result


def pose_matrix(pose: Pose) -> Matrix:
    """Convert a validated pose to a homogeneous matrix."""
    result = np.eye(4)
    result[:3, :3] = Rotation.from_quat(pose.quaternion_xyzw).as_matrix()
    result[:3, 3] = pose.position_m
    return result


def matrix_pose(matrix: Matrix) -> Pose:
    """Validate a rigid transform before conversion to an immutable pose."""
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("Expected finite 4x4 transform")
    rotation = matrix[:3, :3]
    if (
        not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-10, rtol=0)
        or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-10, rtol=0)
        or not np.isclose(np.linalg.det(rotation), 1, atol=1e-10, rtol=0)
    ):
        raise ValueError("Expected rigid right-handed transform")
    return Pose(
        position_m=tuple(matrix[:3, 3]),
        quaternion_xyzw=tuple(Rotation.from_matrix(rotation).as_quat()),
    )
