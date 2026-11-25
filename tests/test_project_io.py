"""Portable mesh round trips, atomic writes and malformed project rejection."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
import trimesh

from robotstudio_ai.core.project_io import (
    CameraState,
    SceneProject,
    import_mesh,
    load_project,
    save_project,
)
from robotstudio_ai.core.scene import MeshShape, SceneDocument, SceneObject, SceneRobot
from robotstudio_ai.core.schema import JointState, Pose
from robotstudio_ai.scene_profiles import load_robot_source, source_from_settings
from robotstudio_ai.settings import generic_config_path, load_settings


@pytest.fixture
def document():
    settings, model = load_settings(generic_config_path())
    robot = SceneRobot(
        source=source_from_settings(settings),
        tool_link="tool0",
        joints=JointState(
            names=tuple(j.name for j in model.active_joints), positions=settings.robot.home_rad
        ),
    )
    return SceneDocument(robot=robot)


@pytest.mark.parametrize("extension", ["stl", "obj"])
@pytest.mark.parametrize("units,scale", [("mm", 0.001), ("m", 1.0)])
def test_mesh_import_units_and_original_origin(tmp_path, extension, units, scale):
    mesh = trimesh.creation.box(extents=[100, 50, 25])
    mesh.apply_translation([20, 30, 40])
    path = tmp_path / f"source.{extension}"
    mesh.export(path)
    asset, center = import_mesh(path, tmp_path / "cache", units=units)
    np.testing.assert_allclose(asset.extents_m, np.array([100, 50, 25]) * scale)
    np.testing.assert_allclose(center, np.array([20, 30, 40]) * scale)
    restored = trimesh.load(asset.path, process=False)
    np.testing.assert_allclose(restored.bounds + center, mesh.bounds * scale, atol=1e-6)
    assert hashlib.sha256(Path(asset.path).read_bytes()).hexdigest() == asset.id


def test_archive_survives_original_mesh_removal_and_new_cache(document, tmp_path):
    source = tmp_path / "user.stl"
    trimesh.creation.icosphere(subdivisions=1, radius=50).export(source)
    asset, center = import_mesh(source, tmp_path / "cache")
    obj = SceneObject(name="mesh", shape=MeshShape(asset_id=asset.id), pose=Pose(position_m=center))
    document = document.model_copy(update={"assets": (asset,), "objects": (obj,)})
    camera = CameraState(position=(2, 2, 2), focal_point=(0, 0, 0), view_up=(0, 0, 1))
    archive_path = tmp_path / "project.rsai"
    save_project(archive_path, SceneProject(scene=document, camera=camera))
    source.unlink()
    Path(asset.path).unlink()
    restored = load_project(archive_path, tmp_path / "new-cache")
    assert restored.scene.objects == document.objects
    assert restored.camera == camera
    assert Path(restored.scene.assets[0].path).is_file()
    settings, model = load_robot_source(restored.scene.robot.source)
    assert settings is not None and model.provenance.synthetic
    with ZipFile(archive_path) as archive:
        metadata = archive.read("scene.json").decode()
        assert str(tmp_path) not in metadata
        assert len(archive.namelist()) == 2


def test_bad_asset_does_not_overwrite_existing_project(document, tmp_path):
    source = tmp_path / "user.stl"
    trimesh.creation.box().export(source)
    asset, _ = import_mesh(source, tmp_path / "cache", units="m")
    document = document.model_copy(
        update={
            "assets": (asset,),
            "objects": (SceneObject(name="A", shape=MeshShape(asset_id=asset.id)),),
        }
    )
    target = tmp_path / "project.rsai"
    save_project(target, SceneProject(scene=document))
    baseline = target.read_bytes()
    Path(asset.path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        save_project(target, SceneProject(scene=document))
    assert target.read_bytes() == baseline


@pytest.mark.parametrize(
    "attack", ["traversal", "duplicate", "bad_hash", "unknown_format", "bad_json"]
)
def test_bad_archives_rejected(document, tmp_path, attack):
    path = tmp_path / "bad.rsai"
    metadata = SceneProject(scene=document).model_dump(mode="json")
    if attack == "unknown_format":
        metadata["format"] = "future-v99"
    with ZipFile(path, "w") as archive:
        archive.writestr("scene.json", "{" if attack == "bad_json" else json.dumps(metadata))
        if attack == "traversal":
            archive.writestr("../outside.stl", "bad")
        elif attack == "duplicate":
            archive.writestr("scene.json", json.dumps(metadata))
        elif attack == "bad_hash":
            archive.writestr("assets/" + "0" * 64 + ".stl", "bad")
    with pytest.raises(ValueError):
        load_project(path, tmp_path / "cache")
    assert not (tmp_path.parent / "outside.stl").exists()


def test_invalid_geometry_and_cache_corruption(tmp_path):
    path = tmp_path / "empty.stl"
    path.write_text("solid empty\nendsolid empty", encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        import_mesh(path, tmp_path / "cache")
    trimesh.creation.box().export(path)
    with pytest.raises(ValueError):
        import_mesh(path, tmp_path / "cache", units="inches")
    asset, _ = import_mesh(path, tmp_path / "cache")
    Path(asset.path).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="cache"):
        import_mesh(path, tmp_path / "cache")


def test_camera_rejects_degenerate_view():
    with pytest.raises(ValueError):
        CameraState(position=(0, 0, 0), focal_point=(0, 0, 0), view_up=(0, 0, 1))
    with pytest.raises(ValueError):
        CameraState(position=(0, 0, 1), focal_point=(0, 0, 0), view_up=(0, 0, 1))
