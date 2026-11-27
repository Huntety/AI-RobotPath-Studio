"""Scene data and editing history independent of Qt, VTK and planning engines."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID, uuid4

import numpy as np
from pydantic import Field, JsonValue, model_validator

from robotstudio_ai.core.collision_settings import CollisionSettings
from robotstudio_ai.core.schema import Finite, JointState, Pose, Record, Vec3
from robotstudio_ai.core.transforms import Matrix, matrix_pose, pose_matrix

LOGGER = logging.getLogger(__name__)
ObjectKind = Literal[
    "worktable",
    "workpiece",
    "obstacle",
    "gripper",
    "pallet",
    "conveyor",
    "jig",
    "fence",
    "target",
    "coordinate_frame",
    "forbidden_zone",
    "custom",
]


class BoxShape(Record):
    kind: Literal["box"] = "box"
    size_m: Vec3 = (0.1, 0.1, 0.1)

    @model_validator(mode="after")
    def positive_size(self):
        if min(self.size_m) <= 0:
            raise ValueError("Box dimensions must be positive")
        return self


class CylinderShape(Record):
    kind: Literal["cylinder"] = "cylinder"
    radius_m: Finite = Field(default=0.05, gt=0)
    height_m: Finite = Field(default=0.1, gt=0)


class SphereShape(Record):
    kind: Literal["sphere"] = "sphere"
    radius_m: Finite = Field(default=0.05, gt=0)


class MeshShape(Record):
    kind: Literal["mesh"] = "mesh"
    asset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    scale: Vec3 = (1.0, 1.0, 1.0)

    @model_validator(mode="after")
    def positive_scale(self):
        if min(self.scale) <= 0:
            raise ValueError("Mesh scale must be positive")
        return self


class FrameShape(Record):
    kind: Literal["frame"] = "frame"
    size_m: Finite = Field(default=0.1, gt=0)


Shape = Annotated[
    BoxShape | CylinderShape | SphereShape | MeshShape | FrameShape, Field(discriminator="kind")
]


class MeshAsset(Record):
    """Immutable content-addressed SI STL; original absolute paths are not exported."""

    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    path: str
    source_name: str = Field(min_length=1, max_length=255)
    extents_m: Vec3


class SceneObject(Record):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=128)
    kind: ObjectKind = "obstacle"
    shape: Shape = BoxShape()
    pose: Pose = Pose()
    parent_frame: str = "world"
    mass_kg: Finite = Field(default=0, ge=0)
    visible: bool = True
    collision_enabled: bool = True
    fixed: bool = True
    task_target: bool = False
    rgba: tuple[Finite, Finite, Finite, Finite] = (0.40, 0.72, 0.82, 1.0)
    properties: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_display(self):
        if not self.name.strip() or any(v < 0 or v > 1 for v in self.rgba):
            raise ValueError("Object needs a nonblank name and RGBA in [0, 1]")
        json.dumps(self.properties, allow_nan=False)
        return self


class RobotSource(Record):
    """Portable builtin/local model identifiers; custom file references stay explicit."""

    kind: Literal["builtin", "local_s922", "profile", "urdf"]
    model_id: str
    path: str | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def reference(self):
        if (self.kind in {"profile", "urdf"}) != bool(self.path):
            raise ValueError("Custom model references require a path; portable identifiers do not")
        return self


class SceneRobot(Record):
    id: UUID = Field(default_factory=uuid4)
    source: RobotSource
    joints: JointState
    base: Pose = Pose()
    tool_offset: Pose = Pose()
    tool_link: str
    visible: bool = True


class SceneDocument(Record):
    format: Literal["robotstudio-scene-v1"] = "robotstudio-scene-v1"
    id: UUID = Field(default_factory=uuid4)
    robot: SceneRobot
    objects: tuple[SceneObject, ...] = Field(default=(), max_length=1000)
    assets: tuple[MeshAsset, ...] = ()
    collision: CollisionSettings = CollisionSettings()

    @model_validator(mode="after")
    def graph_integrity(self):
        ids = [str(o.id) for o in self.objects]
        if len(set(ids)) != len(ids) or str(self.robot.id) in ids:
            raise ValueError("Scene IDs must be unique")
        names = [o.name.strip().casefold() for o in self.objects]
        if len(set(names)) != len(names):
            raise ValueError("Scene object names must be unique")
        asset_ids = [a.id for a in self.assets]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("Asset IDs must be unique")
        parents = {str(o.id): o.parent_frame for o in self.objects}
        for obj in self.objects:
            if isinstance(obj.shape, MeshShape) and obj.shape.asset_id not in asset_ids:
                raise ValueError(f"Missing mesh asset for {obj.name}")
            current, visited = str(obj.id), set()
            while current in parents:
                if current in visited:
                    raise ValueError("Scene parent graph contains a cycle")
                visited.add(current)
                if len(visited) > 100:
                    raise ValueError("Scene hierarchy exceeds 100 levels")
                current = parents[current]
            if current not in {"world", "robot_base", "robot_tool"}:
                raise ValueError(f"Unknown parent frame: {current}")
        return self


@dataclass(frozen=True)
class SceneToken:
    scene_id: UUID
    revision: int


@dataclass(frozen=True)
class SceneChange:
    label: str
    revision: int


@dataclass
class HistoryEntry:
    before: SceneDocument
    after: SceneDocument
    label: str
    key: str | None


class SceneManager:
    """Transactional edits, bounded undo/redo and monotonically increasing revisions.

    Tokens identify input state only; they do not certify collision/path safety.
    Undo also advances revision, preventing stale validation from becoming current.
    """

    def __init__(self, document: SceneDocument, history_limit: int = 100):
        if history_limit < 1:
            raise ValueError("History limit must be positive")
        self._document = SceneDocument.model_validate(document.model_dump()).model_copy(deep=True)
        self._revision = 0
        self._saved_document = self._document.model_copy(deep=True)
        self._undo: list[HistoryEntry] = []
        self._redo: list[HistoryEntry] = []
        self._listeners: list[Callable[[SceneChange], None]] = []
        self.history_limit = history_limit

    @property
    def document(self) -> SceneDocument:
        return self._document.model_copy(deep=True)

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def dirty(self) -> bool:
        return self._document != self._saved_document

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    def subscribe(self, callback: Callable[[SceneChange], None]) -> None:
        self._listeners.append(callback)

    def token(self) -> SceneToken:
        return SceneToken(self._document.id, self._revision)

    def is_current(self, token: SceneToken) -> bool:
        return token == self.token()

    def mark_saved(self, document: SceneDocument | None = None) -> None:
        self._saved_document = (document or self._document).model_copy(deep=True)

    def end_gesture(self) -> None:
        if self._undo:
            self._undo[-1].key = None

    def _notify(self, label: str) -> None:
        self._revision += 1
        change = SceneChange(label, self._revision)
        for callback in tuple(self._listeners):
            try:
                callback(change)
            except Exception:
                LOGGER.exception("Scene listener failed after committed change")

    def replace(
        self,
        document: SceneDocument,
        label: str,
        *,
        key: str | None = None,
        reset_history: bool = False,
    ) -> None:
        """Validate the complete candidate before changing current state."""
        candidate = SceneDocument.model_validate(document.model_dump()).model_copy(deep=True)
        if candidate == self._document:
            return
        if reset_history:
            self._undo.clear()
        elif key and self._undo and self._undo[-1].key == key:
            self._undo[-1].after = candidate
        else:
            self._undo.append(HistoryEntry(self._document, candidate, label, key))
            self._undo = self._undo[-self.history_limit :]
        self._redo.clear()
        self._document = candidate
        self._notify(label)

    def reset(self, document: SceneDocument) -> None:
        candidate = SceneDocument.model_validate(document.model_dump()).model_copy(deep=True)
        self._document = candidate
        self._undo.clear()
        self._redo.clear()
        self.mark_saved()
        self._notify("작업환경 불러오기")

    def get_object(self, object_id: UUID | str) -> SceneObject:
        for obj in self._document.objects:
            if str(obj.id) == str(object_id):
                return obj.model_copy(deep=True)
        raise KeyError(str(object_id))

    def unique_name(self, desired: str) -> str:
        names = {o.name.strip().casefold() for o in self._document.objects}
        if desired.casefold() not in names:
            return desired
        index = 2
        while f"{desired} {index}".casefold() in names:
            index += 1
        return f"{desired} {index}"

    def add(self, obj: SceneObject, asset: MeshAsset | None = None) -> None:
        assets = self._document.assets
        if asset and asset.id not in {a.id for a in assets}:
            assets += (asset,)
        self.replace(
            self._document.model_copy(
                update={"objects": self._document.objects + (obj,), "assets": assets}
            ),
            f"{obj.name} 추가",
        )

    def update_object(self, obj: SceneObject, *, key: str | None = None) -> None:
        if not any(o.id == obj.id for o in self._document.objects):
            raise KeyError(str(obj.id))
        objects = tuple(obj if o.id == obj.id else o for o in self._document.objects)
        self.replace(
            self._document.model_copy(update={"objects": objects}), f"{obj.name} 변경", key=key
        )

    def update_robot(
        self, robot: SceneRobot, *, key: str | None = None, reset_history: bool = False
    ) -> None:
        self.replace(
            self._document.model_copy(update={"robot": robot}),
            "로봇 상태 변경",
            key=key,
            reset_history=reset_history,
        )

    def duplicate(self, object_id: UUID | str) -> UUID:
        source = self.get_object(object_id)
        pose = source.pose.model_copy(
            update={"position_m": (source.pose.position_m[0] + 0.05, *source.pose.position_m[1:])}
        )
        copied = source.model_copy(
            deep=True,
            update={"id": uuid4(), "name": self.unique_name(f"{source.name} 복사"), "pose": pose},
        )
        self.add(copied)
        return copied.id

    def remove(self, object_id: UUID | str) -> None:
        """Remove a subtree as one reversible edit."""
        self.get_object(object_id)
        removed = {str(object_id)}
        while True:
            descendants = {str(o.id) for o in self._document.objects if o.parent_frame in removed}
            if descendants <= removed:
                break
            removed |= descendants
        objects = tuple(o for o in self._document.objects if str(o.id) not in removed)
        pairs = tuple(
            pair
            for pair in self._document.collision.allowed_pairs
            if not any(f"object:{key}" in pair for key in removed)
        )
        collision = self._document.collision.model_copy(update={"allowed_pairs": pairs})
        self.replace(
            self._document.model_copy(update={"objects": objects, "collision": collision}),
            "객체 삭제",
        )

    def undo(self) -> None:
        if self._undo:
            entry = self._undo.pop()
            self._document = entry.before
            self._redo.append(entry)
            self.end_gesture()
            self._notify(f"되돌리기: {entry.label}")

    def redo(self) -> None:
        if self._redo:
            entry = self._redo.pop()
            entry.key = None
            self._document = entry.after
            self._undo.append(entry)
            self._notify(f"다시 실행: {entry.label}")

    def world_transforms(self, tool_world: Matrix | None = None) -> dict[str, Matrix]:
        result = {"world": np.eye(4), "robot_base": pose_matrix(self._document.robot.base)}
        if tool_world is not None:
            result["robot_tool"] = tool_world
        objects = {str(o.id): o for o in self._document.objects}

        def resolve(key: str) -> Matrix:
            if key not in result:
                if key == "robot_tool":
                    raise ValueError("Tool FK transform is required for robot_tool children")
                obj = objects[key]
                result[key] = resolve(obj.parent_frame) @ pose_matrix(obj.pose)
            return result[key]

        for key in objects:
            resolve(key)
        return result

    def reparent(
        self, object_id: UUID | str, parent_frame: str, tool_world: Matrix | None = None
    ) -> None:
        """Change parent while preserving world pose, validating cycles before commit."""
        transforms = self.world_transforms(tool_world)
        obj = self.get_object(object_id)
        pose = matrix_pose(np.linalg.inv(transforms[parent_frame]) @ transforms[str(obj.id)])
        self.update_object(obj.model_copy(update={"parent_frame": parent_frame, "pose": pose}))
