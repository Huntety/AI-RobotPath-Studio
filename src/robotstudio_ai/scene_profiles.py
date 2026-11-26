"""Resolve saved robot references locally without network calls or code execution."""

import hashlib
import json
from pathlib import Path

from robotstudio_ai.core.robot_model import RobotModel
from robotstudio_ai.core.scene import RobotSource
from robotstudio_ai.core.urdf import load_urdf
from robotstudio_ai.settings import (
    AppSettings,
    generic_config_path,
    load_settings,
    s922_config_path,
)


def model_fingerprint(model: RobotModel) -> str:
    """Identify geometry bytes and kinematics rather than trusting a model name."""
    mesh_hashes = {}

    def geometry(value):
        mesh_hash = None
        if value.mesh_path is not None:
            path = value.mesh_path.resolve()
            if path not in mesh_hashes:
                mesh_hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
            mesh_hash = mesh_hashes[path]
        return dict(
            kind=value.kind,
            size=value.size,
            origin=value.origin.tolist(),
            rgba=value.rgba,
            mesh_sha256=mesh_hash,
        )

    payload = dict(
        name=model.name,
        root=model.root_link,
        coordinates=model.provenance.joint_coordinates,
        links=[
            dict(
                name=name,
                visuals=[geometry(g) for g in link.visuals],
                collisions=[geometry(g) for g in link.collisions],
            )
            for name, link in model.links.items()
        ],
        joints=[
            dict(
                name=j.name,
                kind=j.kind,
                parent=j.parent,
                child=j.child,
                origin=j.origin.tolist(),
                axis=j.axis,
                lower=j.lower,
                upper=j.upper,
                velocity=j.velocity,
            )
            for j in model.joints
        ],
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def source_from_settings(settings: AppSettings, model: RobotModel | None = None) -> RobotSource:
    path = settings.config_path
    model_id = settings.robot.provenance.model_id
    if path == generic_config_path().resolve():
        result = RobotSource(kind="builtin", model_id=model_id)
    elif path == s922_config_path().resolve():
        result = RobotSource(kind="local_s922", model_id=model_id)
    elif path is None:
        raise ValueError("A model profile needs a known source path for project persistence")
    else:
        result = RobotSource(kind="profile", model_id=model_id, path=str(path))
    return result.model_copy(update={"fingerprint": model_fingerprint(model)}) if model else result


def load_robot_source(source: RobotSource) -> tuple[AppSettings | None, RobotModel]:
    if source.kind == "urdf":
        model = load_urdf(Path(source.path))
        settings = None
    else:
        path = (
            generic_config_path()
            if source.kind == "builtin"
            else s922_config_path()
            if source.kind == "local_s922"
            else Path(source.path)
        )
        if not path.is_file():
            raise ValueError(
                "Robot model profile is missing. Prepare the S922 CAD or restore the source file."
            )
        settings, model = load_settings(path)
    if model.provenance.model_id != source.model_id:
        raise ValueError("Saved robot identifier does not match the available model")
    if source.fingerprint and model_fingerprint(model) != source.fingerprint:
        raise ValueError("Robot geometry or kinematics changed since this project was saved")
    return settings, model
