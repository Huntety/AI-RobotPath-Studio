"""Strict URDF tree loader. Does not execute xacro, scripts or remote resources."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from xml.etree import ElementTree as ET

import numpy as np

from robotstudio_ai.core.robot_model import Geometry, Joint, Link
from robotstudio_ai.core.schema import ModelProvenance
from robotstudio_ai.core.transforms import Matrix, transform


def numbers(value: str, count: int) -> tuple[float, ...]:
    """Parse exactly count finite numbers from XML attributes."""
    result = tuple(float(item) for item in value.split())
    if len(result) != count or not np.isfinite(result).all():
        raise ValueError(f"Expected {count} finite numbers: {value!r}")
    return result


def origin(element: ET.Element) -> Matrix:
    """Parse an optional origin and expose a read-only transform."""
    node = element.find("origin")
    attrs = {} if node is None else node.attrib
    result = transform(numbers(attrs.get("xyz", "0 0 0"), 3), numbers(attrs.get("rpy", "0 0 0"), 3))
    result.setflags(write=False)
    return result


def required(element: ET.Element, key: str) -> str:
    value = element.get(key, "").strip()
    if not value:
        raise ValueError(f"{element.tag}: missing {key}")
    return value


@dataclass(frozen=True)
class URDFRobot:
    """Validated rooted tree with joints ordered parent before child."""

    name: str
    root_link: str
    links: Mapping[str, Link]
    joints: tuple[Joint, ...]
    active_joints: tuple[Joint, ...]
    provenance: ModelProvenance

    def validate_positions(self, positions: Sequence[float]) -> tuple[float, ...]:
        values = tuple(float(value) for value in positions)
        if len(values) != len(self.active_joints) or not np.isfinite(values).all():
            raise ValueError("Joint vector must be finite and match active joint count")
        for joint, value in zip(self.active_joints, values, strict=True):
            if joint.lower is not None and not joint.lower <= value <= joint.upper:
                raise ValueError(f"{joint.name}: {value:g} outside [{joint.lower}, {joint.upper}]")
        return values


def _geometry(
    element: ET.Element,
    directory: Path,
    materials: dict[str, tuple[float, ...]],
    package_dirs: Mapping[str, Path],
) -> Geometry:
    geometry = element.find("geometry")
    if geometry is None or len(geometry) != 1:
        raise ValueError("Each visual/collision requires exactly one geometry")
    shape = geometry[0]
    mesh_path = None
    match shape.tag:
        case "box":
            size = numbers(required(shape, "size"), 3)
        case "cylinder":
            size = numbers(f"{required(shape, 'radius')} {required(shape, 'length')}", 2)
        case "sphere":
            size = numbers(required(shape, "radius"), 1)
        case "mesh":
            size = numbers(shape.get("scale", "1 1 1"), 3)
            filename = required(shape, "filename")
            if filename.startswith("package://"):
                package, _, relative = filename[10:].partition("/")
                if package not in package_dirs:
                    raise ValueError(f"Explicit package directory required for {package!r}")
                root = package_dirs[package].resolve()
                mesh_path = (root / relative).resolve()
                if not mesh_path.is_relative_to(root):
                    raise ValueError("Mesh escapes its package directory")
            elif "://" in filename:
                raise ValueError("Only local mesh paths are supported")
            else:
                mesh_path = (directory / filename).resolve()
            if mesh_path.suffix.lower() not in {".stl", ".obj"} or not mesh_path.is_file():
                raise ValueError(f"Mesh must be an existing STL/OBJ file: {mesh_path}")
        case _:
            raise ValueError(f"Unsupported geometry: {shape.tag}")
    if any(value <= 0 for value in size):
        raise ValueError("Geometry dimensions/scale must be positive")
    rgba = (0.75, 0.8, 0.88, 1.0)
    material = element.find("material")
    if material is not None:
        color = material.find("color")
        if color is not None:
            rgba = numbers(required(color, "rgba"), 4)
        elif material.get("name") in materials:
            rgba = materials[material.get("name")]
    if any(value < 0 or value > 1 for value in rgba):
        raise ValueError("Material rgba must be between 0 and 1")
    return Geometry(shape.tag, size, origin(element), rgba, mesh_path)


def load_urdf(
    path: Path,
    provenance: ModelProvenance | None = None,
    package_dirs: Mapping[str, Path] | None = None,
) -> URDFRobot:
    """Load a local URDF tree; reject unsupported joints and ambiguous structure."""
    path = Path(path).resolve()
    if path.stat().st_size > 10_000_000:
        raise ValueError("URDF exceeds 10 MB size limit")
    content = path.read_bytes()
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("DTD and XML entities are not supported")
    try:
        robot = ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError(f"Invalid URDF XML: {error}") from error
    if robot.tag != "robot":
        raise ValueError("Expected robot root element")
    name = required(robot, "name")
    materials = {}
    for material in robot.findall("material"):
        color = material.find("color")
        if color is not None:
            materials[required(material, "name")] = numbers(required(color, "rgba"), 4)
    links = {}
    for element in robot.findall("link"):
        link_name = required(element, "name")
        if link_name in links:
            raise ValueError(f"Duplicate link: {link_name}")
        groups = [
            tuple(
                _geometry(item, path.parent, materials, package_dirs or {})
                for item in element.findall(tag)
            )
            for tag in ("visual", "collision")
        ]
        links[link_name] = Link(link_name, *groups)
    joints = []
    names: set[str] = set()
    children: set[str] = set()
    for element in robot.findall("joint"):
        joint_name, kind = required(element, "name"), required(element, "type")
        if joint_name in names or element.find("mimic") is not None:
            raise ValueError(f"Duplicate or unsupported mimic joint: {joint_name}")
        names.add(joint_name)
        if kind not in {"fixed", "revolute", "continuous", "prismatic"}:
            raise ValueError(f"Unsupported joint type: {kind}")
        parent, child = element.find("parent"), element.find("child")
        if parent is None or child is None:
            raise ValueError(f"{joint_name}: parent and child required")
        parent_name, child_name = required(parent, "link"), required(child, "link")
        if parent_name not in links or child_name not in links or child_name in children:
            raise ValueError(f"{joint_name}: invalid links or multiple parents")
        children.add(child_name)
        axis_node = element.find("axis")
        axis = numbers("1 0 0" if axis_node is None else required(axis_node, "xyz"), 3)
        norm = float(np.linalg.norm(axis))
        if kind != "fixed" and norm < 1e-12:
            raise ValueError(f"{joint_name}: axis cannot be zero")
        axis = tuple(v / norm for v in axis) if norm > 0 else (1.0, 0.0, 0.0)
        lower = upper = velocity = None
        if kind != "fixed":
            limit = element.find("limit")
            if limit is None:
                raise ValueError(f"{joint_name}: limits required")
            velocity = numbers(required(limit, "velocity"), 1)[0]
            effort = numbers(required(limit, "effort"), 1)[0]
            if velocity <= 0 or effort <= 0:
                raise ValueError(f"{joint_name}: velocity/effort must be positive")
            if kind != "continuous":
                lower = numbers(required(limit, "lower"), 1)[0]
                upper = numbers(required(limit, "upper"), 1)[0]
                if lower >= upper:
                    raise ValueError(f"{joint_name}: lower limit must be below upper")
        joints.append(
            Joint(
                joint_name,
                kind,
                parent_name,
                child_name,
                origin(element),
                axis,
                lower,
                upper,
                velocity,
            )
        )
    roots = set(links) - children
    if len(roots) != 1:
        raise ValueError("URDF must have exactly one root link")
    root = roots.pop()
    ordered = []
    visited = {root}
    pending = [root]
    while pending:
        parent_name = pending.pop(0)
        for joint in joints:
            if joint.parent == parent_name:
                if joint.child in visited:
                    raise ValueError("URDF contains a cycle")
                visited.add(joint.child)
                ordered.append(joint)
                pending.append(joint.child)
    if len(visited) != len(links):
        raise ValueError("URDF has disconnected links or a cycle")
    provenance = provenance or ModelProvenance(
        model_id=name,
        display_name=f"{name} (unverified)",
        synthetic=False,
        source="User-provided URDF; manufacturer specifications not verified",
    )
    return URDFRobot(
        name,
        root,
        MappingProxyType(links),
        tuple(ordered),
        tuple(j for j in ordered if j.kind != "fixed"),
        provenance,
    )
