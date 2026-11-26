"""Portable scene archives and immutable SI mesh assets; no Qt/VTK dependency."""

import hashlib
import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import numpy as np
import trimesh
from pydantic import Field, model_validator

from robotstudio_ai.core.scene import MeshAsset, MeshShape, SceneDocument
from robotstudio_ai.core.schema import Finite, Record, Vec3

MAX_ASSET_BYTES = 100_000_000
MAX_PROJECT_BYTES = 300_000_000


class CameraState(Record):
    position: Vec3
    focal_point: Vec3
    view_up: Vec3
    parallel: bool = False
    view_angle_deg: Finite = Field(default=30.0, gt=0, lt=180)
    parallel_scale_m: Finite = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def valid_view(self):
        view = np.asarray(self.position) - self.focal_point
        if np.linalg.norm(view) < 1e-9 or np.linalg.norm(np.cross(view, self.view_up)) < 1e-9:
            raise ValueError("Camera needs a nonzero view and a nonparallel up vector")
        return self


class SceneProject(Record):
    format: str = "robotstudio-project-v1"
    scene: SceneDocument
    camera: CameraState | None = None

    @model_validator(mode="after")
    def known_format(self):
        if self.format != "robotstudio-project-v1":
            raise ValueError("Unsupported project format")
        return self


def _store_asset(payload: bytes, cache_dir: Path) -> tuple[str, Path]:
    digest = hashlib.sha256(payload).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{digest}.stl"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Mesh cache is corrupted; original cached file was preserved")
    else:
        descriptor, temporary = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return digest, target.resolve()


def import_mesh(path: Path, cache_dir: Path, *, units: str = "mm") -> tuple[MeshAsset, Vec3]:
    """Centre a triangle mesh in SI, returning its source-origin centre separately.

    Placing the object at this centre preserves the source geometry's world pose.
    OBJ materials/textures are not exported: the portable asset is geometry-only STL.
    """
    path = path.resolve()
    if path.suffix.lower() not in {".stl", ".obj"} or path.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError("Select an STL/OBJ smaller than 100 MB")
    if units not in {"mm", "m"}:
        raise ValueError("Mesh units must be mm or m")
    loaded = trimesh.load(path, force="scene", process=False)
    mesh = loaded.to_mesh()
    if not len(mesh.faces) or len(mesh.faces) > 2_000_000:
        raise ValueError("Mesh must contain 1 to 2,000,000 triangles")
    vertices = np.asarray(mesh.vertices, dtype=float) * (0.001 if units == "mm" else 1.0)
    if not np.isfinite(vertices).all() or not np.isfinite(mesh.faces).all():
        raise ValueError("Mesh contains nonfinite geometry")
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    centered = trimesh.Trimesh(vertices=vertices - center, faces=mesh.faces, process=False)
    if centered.area <= 0:
        raise ValueError("Mesh has no nondegenerate surface")
    payload = centered.export(file_type="stl")
    if len(payload) > MAX_ASSET_BYTES:
        raise ValueError("Converted STL exceeds 100 MB")
    digest, target = _store_asset(payload, cache_dir)
    asset = MeshAsset(
        id=digest,
        path=str(target),
        source_name=path.name,
        extents_m=tuple(np.ptp(vertices, axis=0)),
    )
    return asset, tuple(float(v) for v in center)


def save_project(path: Path, project: SceneProject) -> None:
    """Write one atomic ZIP containing validated JSON and referenced scene meshes.

    Robot CAD/URDF files are references only and are never copied into a project.
    An interrupted write preserves the existing destination.
    """
    project = SceneProject.model_validate(project.model_dump())
    used = {o.shape.asset_id for o in project.scene.objects if isinstance(o.shape, MeshShape)}
    payloads = {}
    assets = []
    total = 0
    for asset in project.scene.assets:
        if asset.id not in used:
            continue
        source = Path(asset.path)
        if source.stat().st_size > MAX_ASSET_BYTES:
            raise ValueError("Scene asset exceeds 100 MB")
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != asset.id:
            raise ValueError(f"Scene asset checksum mismatch: {asset.source_name}")
        total += len(payload)
        if total > MAX_PROJECT_BYTES:
            raise ValueError("Scene assets exceed 300 MB")
        filename = f"assets/{asset.id}.stl"
        payloads[filename] = payload
        assets.append(asset.model_copy(update={"path": filename}))
    portable_scene = project.scene.model_copy(update={"assets": tuple(assets)})
    portable = project.model_copy(update={"scene": portable_scene})
    metadata = portable.model_dump_json(indent=2).encode("utf-8")
    if len(metadata) > 5_000_000:
        raise ValueError("Scene metadata exceeds 5 MB")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(descriptor)
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            archive.writestr("scene.json", metadata)
            for name, payload in payloads.items():
                archive.writestr(name, payload)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_project(path: Path, cache_dir: Path) -> SceneProject:
    """Validate structure, limits and hashes before returning an editable project."""
    if path.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError("Project exceeds 300 MB")
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "scene.json" not in names:
                raise ValueError("Project requires one scene.json and unique ZIP entries")
            if archive.getinfo("scene.json").file_size > 5_000_000:
                raise ValueError("Scene metadata exceeds 5 MB")
            if sum(i.file_size for i in archive.infolist()) > MAX_PROJECT_BYTES + 5_000_000:
                raise ValueError("Expanded project exceeds 305 MB")
            project = SceneProject.model_validate_json(archive.read("scene.json"))
            expected = {"scene.json"}
            verified = []
            for asset in project.scene.assets:
                expected_name = f"assets/{asset.id}.stl"
                if asset.path != expected_name or expected_name not in names:
                    raise ValueError("Asset path does not match its content identifier")
                if archive.getinfo(expected_name).file_size > MAX_ASSET_BYTES:
                    raise ValueError("Expanded mesh asset exceeds 100 MB")
                payload = archive.read(expected_name)
                if hashlib.sha256(payload).hexdigest() != asset.id:
                    raise ValueError("Project mesh checksum mismatch")
                verified.append((asset, payload))
                expected.add(expected_name)
            if set(names) != expected:
                raise ValueError("Project contains unexpected ZIP entries")
    except BadZipFile as error:
        raise ValueError("Invalid RobotStudio project archive") from error
    assets = []
    for asset, payload in verified:
        _, stored = _store_asset(payload, cache_dir)
        assets.append(asset.model_copy(update={"path": str(stored)}))
    return project.model_copy(
        update={"scene": project.scene.model_copy(update={"assets": tuple(assets)})}
    )
