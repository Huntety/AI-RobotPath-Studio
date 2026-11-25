"""Validated configuration and packaged resources shared by CLI and GUI."""

from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import Field

from robotstudio_ai.core.schema import Finite, ModelProvenance, Pose, Record
from robotstudio_ai.core.urdf import URDFRobot, load_urdf


class RobotSettings(Record):
    urdf: str
    provenance: ModelProvenance
    tool_link: str
    home_rad: tuple[Finite, ...]
    base: Pose = Pose()
    tool_offset: Pose = Pose()


class AppSettings(Record):
    robot: RobotSettings
    frame_size_m: Finite = Field(default=0.12, gt=0)


def default_config_path() -> Path:
    return Path(str(files("robotstudio_ai").joinpath("data/config/app.yaml")))


def load_settings(path: Path | None = None) -> tuple[AppSettings, URDFRobot]:
    """Resolve URDF relative to the config file and validate its home/tool frame."""
    path = (path or default_config_path()).resolve()
    settings = AppSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    config = settings.robot
    model = load_urdf(path.parent / config.urdf, config.provenance)
    model.validate_positions(config.home_rad)
    if config.tool_link not in model.links:
        raise ValueError(f"Configured tool link does not exist: {config.tool_link}")
    return settings, model
