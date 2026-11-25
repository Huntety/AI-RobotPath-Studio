"""CAD reference loader contracts, independent reference motions and input rejection."""

import json
from copy import deepcopy

import numpy as np
import pytest
import trimesh
from pydantic import ValidationError

from robotstudio_ai.core.cad_model import load_cad_reference
from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.schema import ModelProvenance
from robotstudio_ai.settings import RobotSettings, default_config_path, generic_config_path


@pytest.fixture
def cad_files(tmp_path):
    mesh = trimesh.creation.box(extents=[0.1, 0.1, 0.1])
    mesh.export(tmp_path / "part.stl")
    manifest = dict(
        format="robotstudio-cad-reference-v1",
        name="fixture_cad",
        parts=[
            dict(name=name, meshes=[dict(filename="part.stl", rgba=[1, 0.5, 0, 1])])
            for name in ("base_link", "link1", "link2")
        ],
        axes=[
            dict(name="J1_CAD", origin_m=[0, 0, 0], direction=[0, 0, 1]),
            dict(name="J2_CAD", origin_m=[1, 0, 0], direction=[0, 1, 0]),
        ],
        flange_world=dict(position_m=[2, 0, 0]),
        source_zip_sha256="a" * 64,
        preview_half_range_deg=180,
    )
    path = tmp_path / "model.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    provenance = ModelProvenance(
        model_id="fixture_cad",
        display_name="CAD test",
        synthetic=False,
        source="Self-authored fixture",
        joint_coordinates="cad_relative",
    )
    return path, provenance, manifest


def test_cad_reference_independent_fk(cad_files):
    path, provenance, _ = cad_files
    model = load_cad_reference(path, provenance)
    solver = TreeKinematics()
    np.testing.assert_allclose(solver.forward(model, [0, 0], "tool0").tcp[:3, 3], [2, 0, 0])
    np.testing.assert_allclose(
        solver.forward(model, [np.pi / 2, 0], "tool0").tcp[:3, 3], [0, 2, 0], atol=1e-12
    )
    np.testing.assert_allclose(
        solver.forward(model, [0, np.pi / 2], "tool0").tcp[:3, 3], [1, 0, -1], atol=1e-12
    )
    assert all(j.velocity is None for j in model.active_joints)
    assert all(not link.collisions for link in model.links.values())


@pytest.mark.parametrize(
    "override",
    [dict(synthetic=True), dict(hardware_validated=True), dict(joint_coordinates="model")],
)
def test_cad_cannot_be_mislabelled(cad_files, override):
    path, provenance, _ = cad_files
    data = provenance.model_dump() | override
    with pytest.raises(ValueError, match="provenance"):
        load_cad_reference(path, ModelProvenance(**data))


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "duplicate",
        "axis",
        "nonfinite",
        "colour",
        "path_escape",
        "missing_mesh",
        "unbounded_preview",
    ],
)
def test_invalid_cad_manifest_rejected(cad_files, change):
    path, provenance, original = cad_files
    manifest = deepcopy(original)
    if change == "count":
        manifest["parts"].pop()
    elif change == "duplicate":
        manifest["parts"][1]["name"] = "base_link"
    elif change == "axis":
        manifest["axes"][0]["direction"] = [0, 0, 0]
    elif change == "nonfinite":
        manifest["axes"][0]["origin_m"] = [float("nan"), 0, 0]
    elif change == "colour":
        manifest["parts"][0]["meshes"][0]["rgba"] = [2, 0, 0, 1]
    elif change == "path_escape":
        manifest["parts"][0]["meshes"][0]["filename"] = "../outside.stl"
    elif change == "missing_mesh":
        manifest["parts"][0]["meshes"][0]["filename"] = "missing.stl"
    elif change == "unbounded_preview":
        manifest["preview_half_range_deg"] = 360
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, ValidationError)):
        load_cad_reference(path, provenance)


def test_config_requires_exactly_one_geometry_source(cad_files):
    _, provenance, _ = cad_files
    data = dict(provenance=provenance, tool_link="tool0", home_rad=[0, 0])
    with pytest.raises(ValidationError):
        RobotSettings(**data)
    with pytest.raises(ValidationError):
        RobotSettings(**data, urdf="r.urdf", cad_manifest="m.json")


def test_default_selection_uses_only_prepared_s922(monkeypatch, tmp_path):
    import robotstudio_ai.settings as settings

    candidate = tmp_path / "models" / "hitbot_s922" / "app.yaml"
    monkeypatch.setattr(settings, "s922_config_path", lambda: candidate)
    assert default_config_path() == generic_config_path()
    candidate.parent.mkdir(parents=True)
    candidate.write_text("", encoding="utf-8")
    assert default_config_path() == candidate


def test_shared_cylinder_axis_requires_unique_line():
    from tools.prepare_s922 import common_axis

    a = [dict(position=[0, 0, 3], direction=[0, 0, 1])]
    b = [dict(position=[0, 0, 10], direction=[0, 0, -1])]
    point, direction = common_axis(a, b)
    np.testing.assert_allclose(point, [0, 0, 0])
    np.testing.assert_allclose(direction, [0, 0, 1])
    with pytest.raises(ValueError):
        common_axis(a, [dict(position=[1, 0, 0], direction=[0, 0, 1])])
    a.append(dict(position=[2, 0, 3], direction=[0, 0, 1]))
    b.append(dict(position=[2, 0, 10], direction=[0, 0, 1]))
    with pytest.raises(ValueError):
        common_axis(a, b)


@pytest.mark.cad_assets
def test_local_official_s922_reconstruction_and_rotations():
    """Local integration, skipped in CI because vendor meshes are not redistributed."""
    from robotstudio_ai.settings import load_settings, s922_config_path

    if not s922_config_path().is_file():
        pytest.skip("Run tools/prepare_s922.py locally")
    settings, model = load_settings(s922_config_path())
    root = s922_config_path().parent
    manifest = json.loads((root / "model.json").read_text(encoding="utf-8"))
    audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
    assert len(model.active_joints) == 6
    assert sum(p["triangles"] for p in audit["parts"]) == 199329
    np.testing.assert_allclose(audit["measured_arm_lengths_mm"], [425, 395], atol=0.01)
    solver = TreeKinematics()
    zero = solver.forward(model, [0] * 6, settings.robot.tool_link)
    np.testing.assert_allclose(zero.tcp[:3, 3], manifest["flange_world"]["position_m"], atol=1e-12)
    # Reassemble all exported vertices and compare each part's original CAD bounds.
    for i, part in enumerate(manifest["parts"]):
        points = np.concatenate(
            [trimesh.load(root / m["filename"], process=False).vertices for m in part["meshes"]]
        )
        homogeneous = np.column_stack((points, np.ones(len(points))))
        world = (zero.links[part["name"]] @ homogeneous.T).T[:, :3]
        bounds = np.r_[world.min(axis=0), world.max(axis=0)]
        np.testing.assert_allclose(bounds, audit["parts"][i]["world_bounds_m"], atol=1e-6)
    # Independent Rodrigues homogeneous rotation around each world-space CAD axis.
    from scipy.linalg import expm

    reference = np.eye(4)
    q = [0.2, -0.3, 0.4, -0.2, 0.1, -0.15]
    for axis, angle in zip(manifest["axes"], q, strict=True):
        point, (x, y, z) = np.array(axis["origin_m"]), axis["direction"]
        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        rotation = expm(skew * angle)
        motion = np.eye(4)
        motion[:3, :3] = rotation
        motion[:3, 3] = point - rotation @ point
        reference = reference @ motion
    np.testing.assert_allclose(
        solver.forward(model, q, "tool0").tcp, reference @ zero.tcp, atol=2e-12
    )
