"""Load articulated CAD reference geometry without inventing controller parameters."""

from pathlib import Path
from types import MappingProxyType
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from robotstudio_ai.core.robot_model import Geometry, Joint, Link
from robotstudio_ai.core.schema import Finite, ModelProvenance, Pose, Record, Vec3
from robotstudio_ai.core.transforms import pose_matrix
from robotstudio_ai.core.urdf import URDFRobot


class CADMesh(Record):
    filename: str
    rgba: tuple[Finite, Finite, Finite, Finite]

    @model_validator(mode="after")
    def valid_material(self):
        if any(value < 0 or value > 1 for value in self.rgba):
            raise ValueError("RGBA values must be in [0, 1]")
        return self


class CADPart(Record):
    name: str = Field(min_length=1)
    meshes: tuple[CADMesh, ...] = Field(min_length=1)


class CADAxis(Record):
    name: str = Field(min_length=1)
    origin_m: Vec3
    direction: Vec3

    @model_validator(mode="after")
    def unit_axis(self):
        if not np.isclose(np.linalg.norm(self.direction), 1.0, atol=1e-8, rtol=0):
            raise ValueError("CAD joint axis must be a unit vector")
        return self


class CADManifest(Record):
    format: Literal["robotstudio-cad-reference-v1"]
    name: str = Field(min_length=1)
    parts: tuple[CADPart, ...]
    axes: tuple[CADAxis, ...] = Field(min_length=1)
    flange_world: Pose
    source_zip_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_half_range_deg: Finite = Field(default=180, gt=0, le=180)

    @model_validator(mode="after")
    def serial_chain(self):
        if len(self.parts) != len(self.axes) + 1:
            raise ValueError("CAD chain requires one base plus one part per joint")
        names = [p.name for p in self.parts] + [a.name for a in self.axes] + ["flange", "tool0"]
        if len(names) != len(set(names)):
            raise ValueError("CAD link/joint names must be unique and exclude flange/tool0")
        return self


def load_cad_reference(path: Path, provenance: ModelProvenance) -> URDFRobot:
    """A positional preview with CAD-relative angles; speed/effort are deliberately absent.

    All reference link frames share world orientation at zero. Each part mesh is
    stored relative to its corresponding axis point. Joint signs and zero offsets
    are geometric conventions, not manufacturer controller coordinates.
    """
    if (
        provenance.synthetic
        or provenance.hardware_validated
        or provenance.joint_coordinates != "cad_relative"
    ):
        raise ValueError("CAD reference provenance must explicitly be uncalibrated/cad_relative")
    path = path.resolve()
    manifest = CADManifest.model_validate_json(path.read_text(encoding="utf-8"))
    frame_origins = [np.zeros(3)] + [np.array(axis.origin_m) for axis in manifest.axes]
    links = {}
    identity = np.eye(4)
    identity.setflags(write=False)
    for part in manifest.parts:
        visuals = []
        for item in part.meshes:
            mesh = (path.parent / item.filename).resolve()
            if (
                Path(item.filename).is_absolute()
                or not mesh.is_relative_to(path.parent)
                or mesh.suffix.lower() not in {".stl", ".obj"}
                or not mesh.is_file()
            ):
                raise ValueError(
                    f"CAD mesh must be a local STL/OBJ within model directory: {item.filename}"
                )
            visuals.append(Geometry("mesh", (1.0, 1.0, 1.0), identity, item.rgba, mesh))
        # A visual mesh is not silently promoted to a verified collision model.
        links[part.name] = Link(part.name, tuple(visuals), ())
    joints = []
    half_range = np.deg2rad(manifest.preview_half_range_deg)
    for i, axis in enumerate(manifest.axes):
        origin = np.eye(4)
        origin[:3, 3] = frame_origins[i + 1] - frame_origins[i]
        origin.setflags(write=False)
        joints.append(
            Joint(
                axis.name,
                "revolute",
                manifest.parts[i].name,
                manifest.parts[i + 1].name,
                origin,
                axis.direction,
                -half_range,
                half_range,
                None,
            )
        )
    active = tuple(joints)
    flange_origin = pose_matrix(manifest.flange_world)
    flange_origin[:3, 3] -= frame_origins[-1]
    flange_origin.setflags(write=False)
    for link_name in ("flange", "tool0"):
        links[link_name] = Link(link_name, (), ())
    joints.extend(
        (
            Joint(
                "flange_fixed",
                "fixed",
                manifest.parts[-1].name,
                "flange",
                flange_origin,
                (1.0, 0.0, 0.0),
                None,
                None,
                None,
            ),
            Joint(
                "tool_fixed",
                "fixed",
                "flange",
                "tool0",
                identity,
                (1.0, 0.0, 0.0),
                None,
                None,
                None,
            ),
        )
    )
    return URDFRobot(
        manifest.name,
        manifest.parts[0].name,
        MappingProxyType(links),
        tuple(joints),
        active,
        provenance,
    )
