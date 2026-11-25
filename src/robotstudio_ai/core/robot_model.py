"""Manufacturer-independent model records and model interface."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from robotstudio_ai.core.schema import ModelProvenance
from robotstudio_ai.core.transforms import Matrix


@dataclass(frozen=True)
class Geometry:
    """Visual/collision primitive; dimensions in SI and mesh-local scale."""

    kind: str
    size: tuple[float, ...]
    origin: Matrix
    rgba: tuple[float, ...] = (0.75, 0.8, 0.88, 1.0)
    mesh_path: Path | None = None


@dataclass(frozen=True)
class Link:
    """Separate visual and collision geometry; inertial simulation is deferred."""

    name: str
    visuals: tuple[Geometry, ...]
    collisions: tuple[Geometry, ...]


@dataclass(frozen=True)
class Joint:
    """URDF origin followed by local-axis motion; SI limits."""

    name: str
    kind: str
    parent: str
    child: str
    origin: Matrix
    axis: tuple[float, ...]
    lower: float | None
    upper: float | None
    velocity: float | None


class RobotModel(Protocol):
    """Data contract independent of loader, renderer and kinematics backend."""

    name: str
    root_link: str
    links: Mapping[str, Link]
    joints: tuple[Joint, ...]
    active_joints: tuple[Joint, ...]
    provenance: ModelProvenance

    def validate_positions(self, positions: Sequence[float]) -> tuple[float, ...]:
        """Return finite, ordered positions; reject any limit violation."""
        ...
