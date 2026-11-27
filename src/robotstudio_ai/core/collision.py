"""FCL rigid geometry queries and conservative checks of joint-linear edges.

No dynamics or independent approximate kinematic chain is introduced. Meshes are
explicit conservative convex hulls; missing robot collision geometry fails closed
unless visual fallback is deliberately requested in the scene collision policy.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import fcl
import numpy as np
import trimesh

from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.core.robot_model import Geometry, RobotModel
from robotstudio_ai.core.scene import (
    BoxShape,
    CylinderShape,
    FrameShape,
    MeshShape,
    SceneDocument,
    SceneManager,
    SceneToken,
    SphereShape,
)


@dataclass(frozen=True)
class PairDistance:
    a: str
    b: str
    distance_m: float
    point_a: tuple[float, ...]
    point_b: tuple[float, ...]
    intersecting: bool = False
    penetration_m: float = 0.0


@dataclass(frozen=True)
class CollisionReport:
    token: SceneToken
    positions: tuple[float, ...]
    complete: bool
    violations: tuple[PairDistance, ...]
    closest: PairDistance | None
    margin_m: float
    checked_pairs: int
    excluded_pairs: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]

    @property
    def clear(self) -> bool:
        return self.complete and not self.violations


@dataclass(frozen=True)
class EdgeReport:
    token: SceneToken
    clear: bool
    complete: bool
    samples_checked: int
    samples_required: int
    interval_motion_bound_m: float
    effective_margin_m: float
    failure_fraction: float | None
    report: CollisionReport | None
    reason: str


class CollisionChecker(Protocol):
    def check(self, positions, *, margin_m: float | None = None) -> CollisionReport: ...
    def check_edge(self, start, end) -> EdgeReport: ...


@dataclass
class CollisionPart:
    owner: str
    frame: str
    local: np.ndarray
    shape: object
    body: object
    radius_m: float
    robot: bool
    attached: str | None


def _native_geometry(geometry: Geometry):
    """Return a native solid, local pose and bounding radius about that pose."""
    matrix = np.array(geometry.origin, copy=True)
    match geometry.kind:
        case "box":
            return fcl.Box(*geometry.size), matrix, np.linalg.norm(geometry.size) / 2, False
        case "sphere":
            return fcl.Sphere(geometry.size[0]), matrix, geometry.size[0], False
        case "cylinder":
            radius, height = geometry.size
            return fcl.Cylinder(radius, height), matrix, np.hypot(radius, height / 2), False
        case "mesh":
            path = geometry.mesh_path
            if path is None or path.stat().st_size > 100_000_000:
                raise ValueError("Collision mesh missing or exceeds 100 MB")
            mesh = trimesh.load(path, force="scene", process=False).to_mesh()
            if not len(mesh.faces) or len(mesh.faces) > 2_000_000:
                raise ValueError("Collision mesh must have 1..2,000,000 triangles")
            vertices = np.asarray(mesh.vertices) * geometry.size
            if not np.isfinite(vertices).all():
                raise ValueError("Collision geometry contains nonfinite vertices")
            extents = np.ptp(vertices, axis=0)
            if np.linalg.matrix_rank(vertices - vertices.mean(axis=0)) < 3:
                centre = (vertices.max(axis=0) + vertices.min(axis=0)) / 2
                translation = np.eye(4)
                translation[:3, 3] = centre
                # A thin enclosing box handles open planar CAD material patches.
                size = np.maximum(extents, 2e-6)
                return fcl.Box(*size), matrix @ translation, np.linalg.norm(size) / 2, True
            hull = trimesh.Trimesh(vertices=vertices, faces=mesh.faces, process=False).convex_hull
            faces = np.column_stack((np.full(len(hull.faces), 3), hull.faces)).ravel()
            shape = fcl.Convex(np.asarray(hull.vertices), len(hull.faces), faces)
            return shape, matrix, float(np.linalg.norm(vertices, axis=1).max()), True
        case _:
            raise ValueError(f"Unsupported collision geometry: {geometry.kind}")


class FCLSceneChecker:
    """One isolated, worker-owned native scene; do not share it across threads."""

    def __init__(self, model: RobotModel, document: SceneDocument, token: SceneToken):
        self.document = SceneDocument.model_validate(document.model_dump()).model_copy(deep=True)
        if token.scene_id != document.id:
            raise ValueError("Scene token/document ID mismatch")
        self.model, self.token = model, token
        robot = self.document.robot
        if robot.joints.names != tuple(j.name for j in model.active_joints):
            raise ValueError("Collision scene/model joint name mismatch")
        if robot.source.model_id != model.provenance.model_id:
            raise ValueError("Collision scene/model identity mismatch")
        if robot.source.fingerprint is not None:
            from robotstudio_ai.scene_profiles import model_fingerprint

            if robot.source.fingerprint != model_fingerprint(model):
                raise ValueError("Robot model fingerprint changed")
        model.validate_positions(robot.joints.positions)
        self.policy = document.collision
        self.solver = TreeKinematics()
        self.manager = SceneManager(document)
        self.parts: list[CollisionPart] = []
        self.warnings: list[str] = []
        self.missing: list[str] = []
        self._parent = {j.child: j.parent for j in model.joints if j.kind == "fixed"}
        self._objects = {str(o.id): o for o in document.objects}
        for name, link in model.links.items():
            geometries = link.collisions
            if not geometries and link.visuals:
                if self.policy.use_visual_fallback:
                    geometries = link.visuals
                    self.warnings.append(f"Visual collision approximation: link:{name}")
                else:
                    self.missing.append(name)
            for geometry in geometries:
                self._add(f"link:{name}", name, geometry, True, None)
        assets = {asset.id: asset for asset in document.assets}
        if not any(part.robot for part in self.parts):
            self.missing.append("robot has no collision bodies")
        for obj in document.objects:
            if not obj.collision_enabled or isinstance(obj.shape, FrameShape):
                continue
            shape = obj.shape
            match shape:
                case BoxShape():
                    geometry = Geometry("box", shape.size_m, np.eye(4))
                case CylinderShape():
                    geometry = Geometry("cylinder", (shape.radius_m, shape.height_m), np.eye(4))
                case SphereShape():
                    geometry = Geometry("sphere", (shape.radius_m,), np.eye(4))
                case MeshShape():
                    asset = assets[shape.asset_id]
                    path = Path(asset.path)
                    if (
                        path.stat().st_size > 100_000_000
                        or hashlib.sha256(path.read_bytes()).hexdigest() != asset.id
                    ):
                        raise ValueError(f"Collision mesh checksum mismatch: {obj.name}")
                    geometry = Geometry("mesh", shape.scale, np.eye(4), mesh_path=path)
                case _:
                    raise ValueError("Unsupported collision shape")
            attached = self._attachment(str(obj.id))
            self._add(f"object:{obj.id}", str(obj.id), geometry, False, attached)
        known = {f"link:{name}" for name in model.links} | {
            f"object:{o.id}" for o in document.objects
        }
        for pair in self.policy.allowed_pairs:
            if not set(pair) <= known:
                raise ValueError(f"Unknown allowed-collision IDs: {pair}")
        manual = {frozenset(pair) for pair in self.policy.allowed_pairs}
        self.pairs, excluded = [], set()
        adjacent = {frozenset((self._rigid(j.parent), self._rigid(j.child))) for j in model.joints}
        for i, a in enumerate(self.parts):
            for b in self.parts[i + 1 :]:
                if a.owner == b.owner:
                    continue
                if not (a.robot or b.robot or a.attached or b.attached):
                    continue  # Only robot/attached geometry moves in a joint pose query.
                skip = frozenset((a.owner, b.owner)) in manual
                if a.robot and b.robot:
                    skip |= (
                        self._rigid(a.frame) == self._rigid(b.frame)
                        or frozenset((self._rigid(a.frame), self._rigid(b.frame))) in adjacent
                    )
                for carried, robot in ((a, b), (b, a)):
                    if carried.attached is not None and robot.robot:
                        skip |= self._rigid(carried.attached) == self._rigid(robot.frame)
                if skip:
                    excluded.add(tuple(sorted((a.owner, b.owner))))
                else:
                    self.pairs.append((a, b))
        if len(self.pairs) > 25000:
            raise ValueError("Collision query exceeds 25,000 part pairs; simplify the scene")
        self.excluded = tuple(sorted(excluded))
        if self.missing:
            self.warnings.append("Missing collision geometry: " + ", ".join(self.missing))
        if model.provenance.joint_coordinates == "cad_relative":
            self.warnings.append("Uncalibrated CAD-relative kinematics; not a hardware validation")

    def _rigid(self, link):
        while link in self._parent:
            link = self._parent[link]
        return link

    def _attachment(self, key):
        frame = self._objects[key].parent_frame
        while frame in self._objects:
            frame = self._objects[frame].parent_frame
        if frame == "robot_tool":
            return self.document.robot.tool_link
        if frame == "robot_base":
            return self.model.root_link
        return None

    def _add(self, owner, frame, geometry, robot, attached):
        shape, local, radius, approximate = _native_geometry(geometry)
        self.parts.append(
            CollisionPart(
                owner,
                frame,
                local,
                shape,
                fcl.CollisionObject(shape),
                float(radius),
                robot,
                attached,
            )
        )
        if approximate:
            self.warnings.append(f"Conservative mesh hull/thin-box approximation: {owner}")

    def check(self, positions, *, margin_m: float | None = None) -> CollisionReport:
        q = self.model.validate_positions(positions)
        margin = self.policy.margin_m if margin_m is None else margin_m
        if not np.isfinite(margin) or margin < 0:
            raise ValueError("Collision margin must be finite and nonnegative")
        robot = self.document.robot
        fk = self.solver.forward(self.model, q, robot.tool_link, robot.base, robot.tool_offset)
        transforms = self.manager.world_transforms(fk.tcp)
        for part in self.parts:
            world = (fk.links[part.frame] if part.robot else transforms[part.frame]) @ part.local
            part.body.setTransform(fcl.Transform(world[:3, :3], world[:3, 3]))
        closest, violations = None, []
        for a, b in self.pairs:
            contact = fcl.CollisionResult()
            intersects = bool(
                fcl.collide(
                    a.body,
                    b.body,
                    fcl.CollisionRequest(num_max_contacts=4, enable_contact=True),
                    contact,
                )
            )
            if intersects:
                points = contact.contacts
                location = np.asarray(points[0].pos) if points else np.zeros(3)
                penetration = max((abs(c.penetration_depth) for c in points), default=0.0)
                pair = PairDistance(
                    a.owner, b.owner, 0.0, tuple(location), tuple(location), True, penetration
                )
            else:
                result = fcl.DistanceResult()
                distance = float(
                    fcl.distance(
                        a.body, b.body, fcl.DistanceRequest(enable_nearest_points=True), result
                    )
                )
                if not np.isfinite(distance) or distance < -1e-7:
                    raise ValueError("FCL returned an invalid distance; result is not clear")
                point_a, point_b = result.nearest_points
                if not np.isfinite([point_a, point_b]).all():
                    raise ValueError("FCL returned invalid nearest points")
                pair = PairDistance(
                    a.owner, b.owner, max(0.0, distance), tuple(point_a), tuple(point_b)
                )
            if closest is None or pair.distance_m < closest.distance_m:
                closest = pair
            if intersects or pair.distance_m <= margin + 1e-9:
                violations.append(pair)
        return CollisionReport(
            self.token,
            q,
            not self.missing,
            tuple(violations),
            closest,
            float(margin),
            len(self.pairs),
            self.excluded,
            tuple(dict.fromkeys(self.warnings)),
        )

    def check_edge(self, start, end) -> EdgeReport:
        """Check q(t)=(1-t)*start+t*end using a conservative displacement envelope.

        Every sample includes margin + maximum inter-sample point displacement.
        A point at any t is within half that bound of its nearest sample, so the
        sum for two moving shapes is bounded by one full interval bound. This
        deliberately overchecks the represented solids; it is not native CCD or
        a claim about unmodelled real hardware/uncertain CAD.
        """
        start = np.array(self.model.validate_positions(start))
        end = np.array(self.model.validate_positions(end))
        delta = np.abs(end - start)
        prismatic_extent = sum(
            max(abs(a), abs(b))
            for j, a, b in zip(self.model.active_joints, start, end, strict=True)
            if j.kind == "prismatic"
        )
        reach = (
            sum(np.linalg.norm(j.origin[:3, 3]) for j in self.model.joints)
            + max((p.radius_m + np.linalg.norm(p.local[:3, 3]) for p in self.parts), default=0)
            + np.linalg.norm(self.document.robot.tool_offset.position_m)
            + sum(np.linalg.norm(o.pose.position_m) for o in self.document.objects)
            + prismatic_extent
        )
        motion = sum(
            float(d) * (1 if j.kind == "prismatic" else reach)
            for j, d in zip(self.model.active_joints, delta, strict=True)
        )
        angle = max(
            (
                float(d)
                for j, d in zip(self.model.active_joints, delta, strict=True)
                if j.kind != "prismatic"
            ),
            default=0,
        )
        intervals = max(
            1,
            int(np.ceil(motion / self.policy.edge_resolution_m)),
            int(np.ceil(angle / self.policy.edge_max_angle_rad)),
        )
        required = intervals + 1
        bound = motion / intervals
        margin = self.policy.margin_m + bound
        if required > self.policy.edge_max_samples:
            return EdgeReport(
                self.token,
                False,
                False,
                0,
                required,
                bound,
                margin,
                None,
                None,
                "sample_budget_exceeded",
            )
        closest_report = None
        for i in range(required):
            report = self.check(start + (end - start) * (i / intervals), margin_m=margin)
            if closest_report is None or (
                report.closest is not None
                and (
                    closest_report.closest is None
                    or report.closest.distance_m < closest_report.closest.distance_m
                )
            ):
                closest_report = report
            if not report.clear:
                return EdgeReport(
                    self.token,
                    False,
                    report.complete,
                    i + 1,
                    required,
                    bound,
                    margin,
                    i / intervals,
                    report,
                    "collision_or_margin" if report.complete else "missing_geometry",
                )
        return EdgeReport(
            self.token,
            True,
            True,
            required,
            required,
            bound,
            margin,
            None,
            closest_report,
            "conservative_envelope_clear",
        )
