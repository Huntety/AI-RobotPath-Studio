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
    """Replaceable FK boundary; IK/Jacobian contracts are added in Phase 3."""

    def forward(
        self,
        model: RobotModel,
        positions: Sequence[float],
        tool_link: str,
        base: Pose = IDENTITY_POSE,
        tool_offset: Pose = IDENTITY_POSE,
    ) -> FKResult: ...


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
