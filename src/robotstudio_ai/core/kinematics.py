"""Tree forward kinematics; no rendering, physics engine or network dependencies."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

import numpy as np
from scipy.spatial.transform import Rotation

from robotstudio_ai.core.robot_model import RobotModel
from robotstudio_ai.core.schema import JointState, Pose
from robotstudio_ai.core.transforms import Matrix, pose_matrix

IDENTITY_POSE = Pose()


@dataclass(frozen=True)
class FKResult:
    """World-space link transforms and TCP using the explicitly selected tool frame."""

    links: Mapping[str, Matrix]
    tcp: Matrix


class KinematicsSolver(Protocol):
    """Replaceable forward and geometric Jacobian boundary."""

    def forward(
        self,
        model: RobotModel,
        positions: Sequence[float],
        tool_link: str,
        base: Pose = IDENTITY_POSE,
        tool_offset: Pose = IDENTITY_POSE,
    ) -> FKResult: ...

    def jacobian(
        self,
        model: RobotModel,
        positions: Sequence[float],
        tool_link: str,
        base: Pose = IDENTITY_POSE,
        tool_offset: Pose = IDENTITY_POSE,
    ) -> Matrix: ...


class TreeKinematics:
    """URDF origin/motion product, including fixed and branched joints."""

    def forward(
        self,
        model: RobotModel,
        positions: Sequence[float],
        tool_link: str,
        base: Pose = IDENTITY_POSE,
        tool_offset: Pose = IDENTITY_POSE,
    ) -> FKResult:
        if tool_link not in model.links:
            raise ValueError(f"Unknown tool link: {tool_link}")
        positions = model.validate_positions(positions)
        values = dict(zip((j.name for j in model.active_joints), positions, strict=True))
        links = {model.root_link: pose_matrix(base)}
        for joint in model.joints:
            motion = np.eye(4)
            if joint.kind in {"revolute", "continuous"}:
                motion[:3, :3] = Rotation.from_rotvec(
                    np.asarray(joint.axis) * values[joint.name]
                ).as_matrix()
            elif joint.kind == "prismatic":
                motion[:3, 3] = np.asarray(joint.axis) * values[joint.name]
            links[joint.child] = links[joint.parent] @ joint.origin @ motion
        tcp = links[tool_link] @ pose_matrix(tool_offset)
        for matrix in (*links.values(), tcp):
            matrix.setflags(write=False)
        return FKResult(MappingProxyType(links), tcp)

    def forward_state(
        self, model: RobotModel, state: JointState, tool_link: str, **kwargs: Pose
    ) -> FKResult:
        """Reject reordered/mismatched joint names at named data boundaries."""
        if state.names != tuple(j.name for j in model.active_joints):
            raise ValueError("Joint state name order does not match model")
        return self.forward(model, state.positions, tool_link, **kwargs)

    def jacobian(
        self,
        model: RobotModel,
        positions: Sequence[float],
        tool_link: str,
        base: Pose = IDENTITY_POSE,
        tool_offset: Pose = IDENTITY_POSE,
    ) -> Matrix:
        """World geometric TCP Jacobian [linear; angular], active-joint name order.

        Only ancestors of the selected tool contribute, including tool offset.
        Prismatic columns have linear velocity only; branch columns remain zero.
        """
        result = self.forward(model, positions, tool_link, base, tool_offset)
        by_child = {joint.child: joint for joint in model.joints}
        ancestors, link = set(), tool_link
        while link in by_child:
            joint = by_child[link]
            ancestors.add(joint.name)
            link = joint.parent
        jacobian = np.zeros((6, len(model.active_joints)))
        for i, joint in enumerate(model.active_joints):
            if joint.name not in ancestors:
                continue
            origin = result.links[joint.parent] @ joint.origin
            axis = origin[:3, :3] @ np.asarray(joint.axis)
            if joint.kind == "prismatic":
                jacobian[:3, i] = axis
            else:
                jacobian[:3, i] = np.cross(axis, result.tcp[:3, 3] - origin[:3, 3])
                jacobian[3:, i] = axis
        jacobian.setflags(write=False)
        return jacobian
