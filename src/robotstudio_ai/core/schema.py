"""Immutable boundary data shared by model, rendering and future planning modules."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Finite = Annotated[float, Field(allow_inf_nan=False)]
Vec3 = tuple[Finite, Finite, Finite]
Quaternion = tuple[Finite, Finite, Finite, Finite]


class Record(BaseModel):
    """Reject unexpected fields and in-place mutations at module boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Pose(Record):
    """Child frame pose in its parent; metres and unit quaternion (x, y, z, w)."""

    position_m: Vec3 = (0.0, 0.0, 0.0)
    quaternion_xyzw: Quaternion = (0.0, 0.0, 0.0, 1.0)

    @field_validator("quaternion_xyzw")
    @classmethod
    def unit_quaternion(cls, value: Quaternion) -> Quaternion:
        """Reject malformed orientation instead of silently normalising input."""
        if not math.isclose(sum(v * v for v in value), 1.0, abs_tol=1e-8):
            raise ValueError("Quaternion must have unit norm")
        return value


class JointState(Record):
    """Ordered joint positions in radians (or metres for prismatic joints)."""

    names: tuple[str, ...]
    positions: tuple[Finite, ...]

    @field_validator("names")
    @classmethod
    def unique_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not name for name in value):
            raise ValueError("Joint names must be nonempty and unique")
        return value

    def model_post_init(self, context: object) -> None:
        if len(self.names) != len(self.positions):
            raise ValueError("Joint names and positions must have equal length")


class ModelProvenance(Record):
    """Keep synthetic models distinct from verified manufacturer specifications."""

    model_id: str
    display_name: str
    synthetic: bool
    source: str
    hardware_validated: bool = False
    joint_coordinates: Literal["model", "cad_relative"] = "model"
