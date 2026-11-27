"""Validated configuration and packaged resources shared by CLI and GUI."""

import sys
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import Field, PrivateAttr, model_validator

from robotstudio_ai.core.cad_model import load_cad_reference
from robotstudio_ai.core.schema import Finite, ModelProvenance, Pose, Record
from robotstudio_ai.core.urdf import URDFRobot, load_urdf


class RobotSettings(Record):
    urdf: str | None = None
    cad_manifest: str | None = None
    provenance: ModelProvenance
    tool_link: str
    home_rad: tuple[Finite, ...]
    base: Pose = Pose()
    tool_offset: Pose = Pose()

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.urdf) == bool(self.cad_manifest):
            raise ValueError("Configure exactly one URDF or CAD reference manifest")
        return self


class AppSettings(Record):
    robot: RobotSettings
    frame_size_m: Finite = Field(default=0.12, gt=0)
    _config_path: Path | None = PrivateAttr(default=None)

    @property
    def config_path(self) -> Path | None:
        return self._config_path


def generic_config_path() -> Path:
    return Path(str(files("robotstudio_ai").joinpath("data/config/app.yaml")))


def model_library_path() -> Path:
    """Local-only manufacturer models beside the executable or source project."""
    base = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[2]
    )
    return base / "models"


def s922_config_path() -> Path:
    return model_library_path() / "hitbot_s922" / "app.yaml"


def default_config_path() -> Path:
    candidate = s922_config_path()
    return candidate if candidate.is_file() else generic_config_path()


def load_settings(path: Path | None = None) -> tuple[AppSettings, URDFRobot]:
    """Resolve URDF relative to the config file and validate its home/tool frame."""
    path = (path or default_config_path()).resolve()
    settings = AppSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    settings._config_path = path
    config = settings.robot
    if config.cad_manifest:
        model = load_cad_reference(path.parent / config.cad_manifest, config.provenance)
    else:
        model = load_urdf(path.parent / config.urdf, config.provenance)
    model.validate_positions(config.home_rad)
    if config.tool_link not in model.links:
        raise ValueError(f"Configured tool link does not exist: {config.tool_link}")
    return settings, model
