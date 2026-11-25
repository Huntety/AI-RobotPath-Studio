"""Resolve saved robot references locally without network calls or code execution."""

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


def source_from_settings(settings: AppSettings) -> RobotSource:
    path = settings.config_path
    model_id = settings.robot.provenance.model_id
    if path == generic_config_path().resolve():
        return RobotSource(kind="builtin", model_id=model_id)
    if path == s922_config_path().resolve():
        return RobotSource(kind="local_s922", model_id=model_id)
    if path is None:
        raise ValueError("A model profile needs a known source path for project persistence")
    return RobotSource(kind="profile", model_id=model_id, path=str(path))


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
    return settings, model
