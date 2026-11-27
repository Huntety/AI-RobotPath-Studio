"""PyVista/VTK view driven only by validated model/FK data."""

import os
from collections.abc import Mapping

os.environ["QT_API"] = "pyside6"

import numpy as np
import pyvista as pv
import trimesh
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from robotstudio_ai.core.kinematics import FKResult
from robotstudio_ai.core.robot_model import Geometry, RobotModel

Surfaces = dict[tuple[str, int], pv.PolyData]


def geometry_surface(geometry: Geometry) -> pv.PolyData:
    """Construct geometry in link coordinates, preserving the URDF visual origin."""
    match geometry.kind:
        case "box":
            surface = pv.Cube(
                center=(0, 0, 0),
                x_length=geometry.size[0],
                y_length=geometry.size[1],
                z_length=geometry.size[2],
            )
        case "cylinder":
            surface = pv.Cylinder(
                center=(0, 0, 0),
                direction=(0, 0, 1),
                radius=geometry.size[0],
                height=geometry.size[1],
                resolution=48,
            )
        case "sphere":
            surface = pv.Sphere(radius=geometry.size[0], theta_resolution=32, phi_resolution=32)
        case "mesh":
            if geometry.mesh_path is None or geometry.mesh_path.stat().st_size > 100_000_000:
                raise ValueError("Mesh missing or larger than Phase 1 limit (100 MB)")
            scene = trimesh.load(geometry.mesh_path, force="scene", process=False)
            mesh = scene.to_mesh()
            if not len(mesh.vertices) or not len(mesh.faces):
                raise ValueError("Mesh contains no triangle faces")
            if len(mesh.faces) > 2_000_000:
                raise ValueError("Mesh exceeds Phase 1 limit (2 million triangles)")
            vertices = np.asarray(mesh.vertices) * np.asarray(geometry.size)
            if not np.isfinite(vertices).all():
                raise ValueError("Mesh contains nonfinite vertices")
            faces = np.column_stack([np.full(len(mesh.faces), 3), mesh.faces]).ravel()
            surface = pv.PolyData(vertices, faces)
        case _:
            raise ValueError(f"Unsupported shape: {geometry.kind}")
    return surface.transform(geometry.origin, inplace=False)


def prepare_surfaces(model: RobotModel) -> Surfaces:
    """CPU/mesh loading may run in a worker; no render window is accessed here."""
    return {
        (name, index): geometry_surface(geometry)
        for name, link in model.links.items()
        for index, geometry in enumerate(link.visuals)
    }


class RobotViewport(QWidget):
    """Actors retain link-local geometry; FK updates actor matrices, not mesh vertices."""

    def __init__(self, parent: QWidget | None = None, off_screen: bool = False):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self, off_screen=off_screen, auto_update=False)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("#101d2b", top="#23364a")
        self.plotter.add_axes(line_width=2)
        self.plotter.enable_trackball_style()
        self.actors: dict[tuple[str, int], pv.Actor] = {}
        self.frames: dict[str, list[pv.Actor]] = {}
        self._frame_visibility = True
        self.last_transforms: Mapping = {}

    def set_model(self, model: RobotModel, surfaces: Surfaces, frame_size: float):
        self.plotter.clear()
        self.actors.clear()
        self.frames.clear()
        floor = pv.Plane(
            center=(0, 0, -0.005),
            direction=(0, 0, 1),
            i_size=2.4,
            j_size=2.4,
            i_resolution=24,
            j_resolution=24,
        )
        self.plotter.add_mesh(
            floor,
            color="#33475a",
            style="wireframe",
            opacity=0.36,
            line_width=1,
            pickable=False,
            render=False,
        )
        for key, surface in surfaces.items():
            geometry = model.links[key[0]].visuals[key[1]]
            self.actors[key] = self.plotter.add_mesh(
                surface,
                color=geometry.rgba[:3],
                opacity=geometry.rgba[3],
                smooth_shading=True,
                specular=0.45,
                specular_power=28,
                render=False,
                name=f"{key[0]}:{key[1]}",
            )
        for name, length in (("base", frame_size), ("tool", frame_size), ("tcp", frame_size * 0.7)):
            actors = []
            for axis, color in zip(np.eye(3), ("#f36d75", "#76d69d", "#6caaff"), strict=True):
                actors.append(
                    self.plotter.add_mesh(
                        pv.Arrow(start=(0, 0, 0), direction=axis, scale=length),
                        color=color,
                        name=f"{name}-{'xyz'[len(actors)]}",
                        render=False,
                        pickable=False,
                    )
                )
            self.frames[name] = actors
        self.show_frames(self._frame_visibility)

    def update_pose(self, result: FKResult, root_link: str, tool_link: str):
        """All actors and coordinate frames consume the same FK result as the TCP panel."""
        for (name, _), actor in self.actors.items():
            actor.user_matrix = result.links[name]
        for name, matrix in (
            ("base", result.links[root_link]),
            ("tool", result.links[tool_link]),
            ("tcp", result.tcp),
        ):
            for actor in self.frames.get(name, []):
                actor.user_matrix = matrix
        self.last_transforms = result.links
        self.plotter.render()

    def show_frames(self, visible: bool):
        self._frame_visibility = visible
        for actors in self.frames.values():
            for actor in actors:
                actor.SetVisibility(visible)
        self.plotter.render()

    def fit(self):
        self.plotter.renderer.view_isometric()
        if self.actors:
            bounds = np.asarray([actor.bounds for actor in self.actors.values()])
            focused = tuple(
                value
                for axis in range(3)
                for value in (bounds[:, 2 * axis].min(), bounds[:, 2 * axis + 1].max())
            )
            self.plotter.renderer.reset_camera(bounds=focused)
        else:
            self.plotter.renderer.reset_camera()
        # view_isometric leaves camera_set false in this PyVista build; mark the
        # fitted camera before its property getter can reset it to floor bounds.
        self.plotter.camera_set = True
        self.plotter.camera.zoom(1.05)
        self.plotter.renderer.ResetCameraClippingRange()
        self.plotter.render()

    def close_view(self):
        self.plotter.close()
