"""Download/convert official S922 STEP to a local-only articulated CAD profile.

OCP is a build-time extra, never needed by the GUI. Joint axes are recovered from
coaxial cylindrical surfaces of neighbouring CAD parts. No DH/zero calibration,
joint velocity/effort, collision or manufacturer control model is fabricated.
"""

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import trimesh
import yaml
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
CAD_URL = "https://cn.hitbot.cc/hitbot/product/arm6/z-arms922/z-arms922.zip"
CAD_SHA256 = "ab3508233adfdcd933543c8c34df2c04a35d06c8d64bab242a32764062d2cd31"
PAGE_URL = "https://en.hitbot.cc/six-axis-collaborative-robotic-arm/55.html"
CAD_TO_WORLD = np.array([[1.0, 0, 0], [0, 0, -1], [0, 1.0, 0]])


def common_axis(first: list[dict], second: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Require one unambiguous coincident line, supported by both adjacent parts."""
    candidates: list[tuple[np.ndarray, np.ndarray]] = []
    for a in first:
        for b in second:
            p, q = np.asarray(a["position"]), np.asarray(b["position"])
            d, other = np.asarray(a["direction"]), np.asarray(b["direction"])
            if abs(d @ other) < 1 - 1e-9 or np.linalg.norm(np.cross(q - p, d)) > 0.005:
                continue
            d = d / np.linalg.norm(d)
            if d[np.argmax(np.abs(d))] < 0:
                d = -d
            anchor = p - d * (d @ p)
            if not any(
                np.linalg.norm(anchor - existing[0]) < 0.01 and abs(d @ existing[1]) > 1 - 1e-9
                for existing in candidates
            ):
                candidates.append((anchor, d))
    if len(candidates) != 1:
        raise ValueError(f"Expected one shared cylindrical joint axis, found {len(candidates)}")
    return candidates[0]


def read_step(path: Path) -> list[dict]:
    """Read XCAF placements, face colours and analytic surfaces with OpenCascade."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_Color
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_DocumentTool

    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError("OpenCascade could not read STEP")
    document = TDocStd_Document(TCollection_ExtendedString("XCAF"))
    if not reader.Transfer(document):
        raise ValueError("STEP assembly transfer failed")
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    colours = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    roots = TDF_LabelSequence()
    shapes.GetFreeShapes(roots)
    parts = []

    def walk(label, location):
        if shapes.IsReference_s(label):
            target = TDF_Label()
            shapes.GetReferredShape_s(label, target)
            location = location.Multiplied(shapes.GetLocation_s(label))
        else:
            target = label
        children = TDF_LabelSequence()
        shapes.GetComponents_s(target, children)
        if children.Length():
            for index in range(1, children.Length() + 1):
                walk(children.Value(index), location)
            return
        shape = shapes.GetShape_s(target)
        name = TDataStd_Name()
        label_name = (
            name.Get().ToExtString() if target.FindAttribute(TDataStd_Name.GetID_s(), name) else ""
        )
        BRepMesh_IncrementalMesh(shape, 0.35, False, 0.22, True)
        vertices, triangles, face_colours, cylinders, planes = [], [], [], [], []
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            moved = TopoDS.Face_s(face.Moved(location))
            surface = BRepAdaptor_Surface(moved)
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(moved, props)
            if surface.GetType() in (GeomAbs_Cylinder, GeomAbs_Plane):
                entity = (
                    surface.Cylinder() if surface.GetType() == GeomAbs_Cylinder else surface.Plane()
                )
                p, d = entity.Location(), entity.Axis().Direction()
                record = dict(
                    position=[p.X(), p.Y(), p.Z()],
                    direction=[d.X(), d.Y(), d.Z()],
                    area=float(props.Mass()),
                )
                if surface.GetType() == GeomAbs_Cylinder and entity.Radius() > 10:
                    cylinders.append(dict(record, radius=float(entity.Radius())))
                elif surface.GetType() == GeomAbs_Plane and props.Mass() > 100:
                    planes.append(record)
            mesh_location = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, mesh_location)
            if tri is not None:
                offset = len(vertices)
                transform = location.Multiplied(mesh_location).Transformation()
                for index in range(1, tri.NbNodes() + 1):
                    p = tri.Node(index).Transformed(transform)
                    vertices.append([p.X(), p.Y(), p.Z()])
                colour = Quantity_Color()
                found = (
                    colours.GetColor(face, XCAFDoc_ColorSurf, colour)
                    or colours.GetColor(shape, XCAFDoc_ColorSurf, colour)
                    or colours.GetColor(target, XCAFDoc_ColorGen, colour)
                )
                rgba = (
                    [
                        round(colour.Red() * 255),
                        round(colour.Green() * 255),
                        round(colour.Blue() * 255),
                        255,
                    ]
                    if found
                    else [210, 220, 228, 255]
                )
                for index in range(1, tri.NbTriangles() + 1):
                    indices = [i - 1 + offset for i in tri.Triangle(index).Get()]
                    if face.Orientation() == TopAbs_REVERSED:
                        indices.reverse()
                    triangles.append(indices)
                    face_colours.append(rgba)
            explorer.Next()
        mesh = trimesh.Trimesh(vertices=vertices, faces=triangles, process=False)
        parts.append(
            dict(
                name=label_name,
                mesh=mesh,
                colours=np.asarray(face_colours),
                cylinders=cylinders,
                planes=planes,
            )
        )

    for index in range(1, roots.Length() + 1):
        walk(roots.Value(index), TopLoc_Location())
    if len(parts) != 7 or any(
        not p["name"].startswith(f"S922-{i + 1}") for i, p in enumerate(parts)
    ):
        raise ValueError("Pinned S922 STEP must contain the seven expected ordered parts")
    return parts


def flange_pose(parts: list[dict], axis: tuple[np.ndarray, np.ndarray]) -> dict:
    """Intersect the last rotation line with the outer flange mounting plane.

    Z points out of the last part. X/Y are a documented CAD frame convention;
    they have not been calibrated to the manufacturer's flange frame.
    """
    anchor, direction = axis
    away = parts[-1]["mesh"].centroid - parts[-2]["mesh"].centroid
    outward = direction if direction @ away > 0 else -direction
    planes = [
        p
        for p in parts[-1]["planes"]
        if p["area"] > 1000 and abs(np.asarray(p["direction"]) @ outward) > 1 - 1e-9
    ]
    if not planes:
        raise ValueError("No flange mounting plane found")
    plane = max(planes, key=lambda p: np.asarray(p["position"]) @ outward)
    normal, point = np.asarray(plane["direction"]), np.asarray(plane["position"])
    center = anchor + direction * ((point - anchor) @ normal) / (direction @ normal)
    z = CAD_TO_WORLD @ outward
    x = np.cross([0, 0, 1], z)
    if np.linalg.norm(x) < 1e-8:
        x = np.cross([0, 1, 0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    rotation = np.column_stack((x, y, z))
    return dict(
        position_m=(CAD_TO_WORLD @ center / 1000).tolist(),
        quaternion_xyzw=Rotation.from_matrix(rotation).as_quat().tolist(),
    )


def convert(zip_path: Path, output: Path) -> dict:
    """Create a fresh local model. Refuse to overwrite an existing model directory."""
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != CAD_SHA256:
        raise ValueError(
            "Official S922 ZIP checksum changed; review the revision before conversion"
        )
    if output.exists():
        raise FileExistsError(f"Output already exists (preserved): {output}")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix="s922-convert-") as temporary:
        work = Path(temporary)
        with ZipFile(zip_path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith((".step", ".stp"))]
            if len(names) != 1 or archive.getinfo(names[0]).file_size > 100_000_000:
                raise ValueError("Expected exactly one STEP smaller than 100 MB")
            step = work / "s922.step"
            step.write_bytes(archive.read(names[0]))
        parts = read_step(step)
        axes = [
            common_axis(a["cylinders"], b["cylinders"])
            for a, b in zip(parts, parts[1:], strict=False)
        ]
        # Independent catalogue/drawing cross-checks, not fitted DH parameters.
        measured = [
            np.linalg.norm(np.cross(axes[j + 1][0] - axes[j][0], axes[j][1])) for j in (1, 2)
        ]
        if not np.allclose(measured, [425.0, 395.0], atol=0.01, rtol=0):
            raise ValueError(f"CAD dimensions disagree with official drawing: {measured}")
        converted = work / "model"
        (converted / "meshes").mkdir(parents=True)
        world_axes = [
            dict(
                name=f"J{i + 1}_CAD",
                origin_m=(CAD_TO_WORLD @ p / 1000).tolist(),
                direction=(CAD_TO_WORLD @ d).tolist(),
            )
            for i, (p, d) in enumerate(axes)
        ]
        origins = [np.zeros(3)] + [np.asarray(a["origin_m"]) for a in world_axes]
        model_parts, audits = [], []
        for index, part in enumerate(parts):
            mesh = part["mesh"]
            colours = part["colours"]
            local_vertices = mesh.vertices @ CAD_TO_WORLD.T / 1000 - origins[index]
            visuals = []
            max_error = 0.0
            for colour_index, rgba in enumerate(np.unique(colours, axis=0)):
                face_ids = np.flatnonzero(np.all(colours == rgba, axis=1))
                subset = trimesh.Trimesh(local_vertices, mesh.faces[face_ids], process=False)
                filename = f"meshes/link{index}-material{colour_index}.stl"
                target = converted / filename
                subset.export(target)
                # STL stores float32 coordinates: bound the actual conversion error.
                restored = trimesh.load(target, process=False)
                expected = subset.triangles.reshape(-1, 3)
                actual = restored.triangles.reshape(-1, 3)
                error = float(np.max(np.abs(expected - actual)))
                max_error = max(max_error, error)
                visuals.append(dict(filename=filename, rgba=(rgba / 255).tolist()))
            if max_error > 1e-6:
                raise ValueError("STL conversion exceeds 1 micrometre tolerance")
            name = "base_link" if index == 0 else f"link{index}"
            model_parts.append(dict(name=name, meshes=visuals))
            audits.append(
                dict(
                    part=index + 1,
                    label=part["name"],
                    triangles=len(mesh.faces),
                    max_stl_error_m=max_error,
                    world_bounds_m=(mesh.vertices @ CAD_TO_WORLD.T / 1000).min(axis=0).tolist()
                    + (mesh.vertices @ CAD_TO_WORLD.T / 1000).max(axis=0).tolist(),
                )
            )
        manifest = dict(
            format="robotstudio-cad-reference-v1",
            name="hitbot_s922_cad_reference",
            parts=model_parts,
            axes=world_axes,
            flange_world=flange_pose(parts, axes[-1]),
            source_zip_sha256=CAD_SHA256,
            preview_half_range_deg=180,
        )
        (converted / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        config = dict(
            robot=dict(
                cad_manifest="model.json",
                provenance=dict(
                    model_id=manifest["name"],
                    display_name="HITBOT S922 · 공식 CAD / 영점 미보정",
                    synthetic=False,
                    hardware_validated=False,
                    joint_coordinates="cad_relative",
                    source=(
                        f"{PAGE_URL} | S922 STEP V3.0 2024-04-29 | "
                        "CAD-reference axes, not calibrated"
                    ),
                ),
                tool_link="tool0",
                home_rad=[0.0] * 6,
            ),
            frame_size_m=0.10,
        )
        (converted / "app.yaml").write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        audit = dict(
            source_page=PAGE_URL,
            download_url=CAD_URL,
            zip_sha256=CAD_SHA256,
            step_sha256=hashlib.sha256(step.read_bytes()).hexdigest(),
            source_member=ascii(names[0]),
            cad_revision="V3.0 2024-04-29",
            parts=audits,
            joint_axes_world=world_axes,
            measured_arm_lengths_mm=[float(v) for v in measured],
            published_limits_deg=[
                [-175, 175],
                [-265, 85],
                [-160, 160],
                [-265, 85],
                [-175, 175],
                [-175, 175],
            ],
            preview_limits_are_controller_limits=False,
            notes="Zero/sign/flange twist uncalibrated; no velocity/effort or collision model",
        )
        (converted / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        converted.rename(output)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--zip", type=Path, help="Previously downloaded, checksum-pinned official ZIP"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "hitbot_s922")
    args = parser.parse_args()
    source = args.zip
    if source is None:
        source = ROOT / ".cache" / "s922-source" / "s922-official.zip"
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            with urllib.request.urlopen(CAD_URL, timeout=60) as response:
                payload = response.read(30_000_001)
            if len(payload) > 30_000_000:
                raise ValueError("CAD ZIP exceeds 30 MB download limit")
            source.write_bytes(payload)
    audit = convert(source.resolve(), args.output.resolve())
    print(
        f"Prepared S922: {len(audit['parts'])} rigid parts; "
        f"{sum(p['triangles'] for p in audit['parts'])} triangles"
    )
    print("CAD-relative preview only; controller zero/sign and kinematics are uncalibrated.")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
