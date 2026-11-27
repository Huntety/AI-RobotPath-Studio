"""Serializable collision policy, independent of the native collision backend."""

from pydantic import Field, model_validator

from robotstudio_ai.core.schema import Finite, Record


class CollisionSettings(Record):
    margin_m: Finite = Field(default=0.005, ge=0, le=1)
    use_visual_fallback: bool = False
    allowed_pairs: tuple[tuple[str, str], ...] = Field(default=(), max_length=2000)
    edge_resolution_m: Finite = Field(default=0.01, ge=0.0001, le=0.1)
    edge_max_angle_rad: Finite = Field(default=0.05, gt=0, le=0.5)
    edge_max_samples: int = Field(default=3000, ge=2, le=20000)

    @model_validator(mode="after")
    def pairs(self):
        normalised = set()
        for a, b in self.allowed_pairs:
            if not a or not b or a == b:
                raise ValueError("Allowed collision pairs need two different nonempty IDs")
            pair = tuple(sorted((a, b)))
            if pair in normalised:
                raise ValueError("Duplicate allowed collision pair")
            normalised.add(pair)
        return self
