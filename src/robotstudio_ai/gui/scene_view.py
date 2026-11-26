"""Scene actors and VTK rigid transform widget, separate from robot rendering."""

from uuid import uuid4

import numpy as np
import pyvista as pv
from PySide6.QtCore import QObject, Signal
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkInteractionWidgets import vtkBoxWidget
from vtkmodules.vtkRenderingCore import vtkPropPicker

from robotstudio_ai.core.robot_model import Geometry
from robotstudio_ai.core.scene import (
    BoxShape,
    CylinderShape,
    FrameShape,
    MeshShape,
    SceneDocument,
    SphereShape,
)
from robotstudio_ai.gui.viewport import RobotViewport, geometry_surface


def object_surface(shape, assets) -> pv.PolyData:
    """Create link-local geometry from the authoritative scene shape and assets."""
    identity = np.eye(4)
    if isinstance(shape, BoxShape):
        return geometry_surface(Geometry("box", shape.size_m, identity))
    if isinstance(shape, CylinderShape):
        return geometry_surface(Geometry("cylinder", (shape.radius_m, shape.height_m), identity))
    if isinstance(shape, SphereShape):
        return geometry_surface(Geometry("sphere", (shape.radius_m,), identity))
    if isinstance(shape, MeshShape):
        from pathlib import Path

        asset = next(a for a in assets if a.id == shape.asset_id)
        return geometry_surface(Geometry("mesh", shape.scale, identity, mesh_path=Path(asset.path)))
    if isinstance(shape, FrameShape):
        arrows = []
        for direction, colour in zip(
            np.eye(3), ((243, 109, 117), (118, 214, 157), (108, 170, 255)), strict=True
        ):
            arrow = pv.Arrow(direction=direction, scale=shape.size_m)
            arrow.cell_data["frame_rgb"] = np.tile(colour, (arrow.n_cells, 1)).astype(np.uint8)
            arrows.append(arrow)
        return arrows[0].merge(arrows[1:], merge_points=False)
    raise ValueError("Unsupported scene shape")


class SceneView(QObject):
    """Render/pick/edit objects. Emits world transforms; never mutates scene data."""

    picked = Signal(str)
    transformed = Signal(str, object, str)
    drag_finished = Signal()

    def __init__(self, viewport: RobotViewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.actors: dict[str, pv.Actor] = {}
        self.surfaces: dict[str, pv.PolyData] = {}
        self.signatures: dict[str, str] = {}
        self.prepared = {}
        self.widget: vtkBoxWidget | None = None
        self.widget_object: str | None = None
        self.dragging = False
        self.gesture_key = ""
        self._press = (0, 0)
        viewport.plotter.iren.add_observer("LeftButtonPressEvent", self._pressed)
        viewport.plotter.iren.add_observer("LeftButtonReleaseEvent", self._released)

    def _pressed(self, caller, event):
        self._press = self.viewport.plotter.iren.interactor.GetEventPosition()

    def _released(self, caller, event):
        point = self.viewport.plotter.iren.interactor.GetEventPosition()
        if not self.dragging and np.linalg.norm(np.subtract(point, self._press)) < 4:
            self.pick_at(*point)

    def pick_at(self, x: int, y: int) -> str:
        picker = vtkPropPicker()
        picker.Pick(x, y, 0, self.viewport.plotter.renderer)
        actor = picker.GetActor()
        for key, candidate in self.actors.items():
            if actor == candidate:
                self.picked.emit(key)
                return key
        if any(actor == candidate for candidate in self.viewport.actors.values()):
            self.picked.emit("robot")
            return "robot"
        # Widget handles are not an instruction to deselect their object.
        if actor is None:
            self.picked.emit("")
        return ""

    def model_was_cleared(self):
        self.clear_widget()
        self.actors.clear()
        self.signatures.clear()
        self.surfaces.clear()
        self.prepared.clear()

    def stage_surfaces(self, document, surfaces):
        for obj in document.objects:
            if str(obj.id) in surfaces:
                self.prepared[obj.shape.model_dump_json()] = surfaces[str(obj.id)]

    def sync(
        self,
        document: SceneDocument,
        transforms: dict,
        selected: str | None,
        manipulate: bool,
        prepared: dict[str, pv.PolyData] | None = None,
    ):
        plotter = self.viewport.plotter
        objects = {str(o.id): o for o in document.objects}
        for key in tuple(self.actors):
            if key not in objects:
                plotter.remove_actor(self.actors.pop(key), render=False)
                self.signatures.pop(key, None)
                self.surfaces.pop(key, None)
        effective_visibility = {
            "world": True,
            "robot_base": document.robot.visible,
            "robot_tool": document.robot.visible,
        }

        def visible(key):
            if key not in effective_visibility:
                obj = objects[key]
                effective_visibility[key] = obj.visible and visible(obj.parent_frame)
            return effective_visibility[key]

        for key, obj in objects.items():
            signature = obj.shape.model_dump_json()
            if self.signatures.get(key) != signature:
                if key in self.actors:
                    plotter.remove_actor(self.actors.pop(key), render=False)
                staged = self.prepared.pop(signature, None)
                surface = (
                    prepared[key]
                    if prepared and key in prepared
                    else staged
                    if staged is not None
                    else object_surface(obj.shape, document.assets)
                )
                self.surfaces[key] = surface
                options = (
                    dict(scalars="frame_rgb", rgb=True) if isinstance(obj.shape, FrameShape) else {}
                )
                self.actors[key] = plotter.add_mesh(
                    surface,
                    color=obj.rgba[:3],
                    opacity=obj.rgba[3],
                    smooth_shading=True,
                    specular=0.25,
                    render=False,
                    reset_camera=False,
                    name=f"scene:{key}",
                    **options,
                )
                self.signatures[key] = signature
            actor = self.actors[key]
            actor.user_matrix = transforms[key]
            actor.SetVisibility(visible(key))
            actor.prop.color = obj.rgba[:3]
            actor.prop.opacity = obj.rgba[3]
            actor.prop.show_edges = key == selected and not isinstance(obj.shape, FrameShape)
            actor.prop.edge_color = "#74e6eb"
            actor.prop.line_width = 2
        for actor in self.viewport.actors.values():
            actor.SetVisibility(document.robot.visible)
        for actors in self.viewport.frames.values():
            for actor in actors:
                actor.SetVisibility(document.robot.visible and self.viewport._frame_visibility)
        if selected in self.actors and self.actors[selected].GetVisibility() and manipulate:
            self._place_widget(selected, transforms[selected])
        elif not self.dragging:
            self.clear_widget()
        plotter.render()

    def _place_widget(self, key: str, matrix):
        if self.dragging:
            return
        if self.widget_object != key:
            self.clear_widget()
            widget = vtkBoxWidget()
            widget.SetInteractor(self.viewport.plotter.iren.interactor)
            widget.SetDefaultRenderer(self.viewport.plotter.renderer)
            widget.SetPlaceFactor(1.05)
            widget.ScalingEnabledOff()
            widget.TranslationEnabledOn()
            widget.RotationEnabledOn()
            widget.GetOutlineProperty().SetColor(0.4, 0.9, 0.95)
            widget.SetHandleSize(0.008)
            widget.AddObserver("StartInteractionEvent", self._start)
            widget.AddObserver("InteractionEvent", self._interact)
            widget.AddObserver("EndInteractionEvent", self._end)
            self.widget, self.widget_object = widget, key
        bounds = list(self.surfaces[key].bounds)
        for axis in range(3):
            if bounds[2 * axis + 1] - bounds[2 * axis] < 0.001:
                bounds[2 * axis] -= 0.001
                bounds[2 * axis + 1] += 0.001
        self.widget.PlaceWidget(bounds)
        transform = vtkTransform()
        transform.SetMatrix(np.asarray(matrix).ravel())
        self.widget.SetTransform(transform)
        self.widget.On()

    def _start(self, caller, event):
        self.dragging = True
        self.gesture_key = str(uuid4())

    def _interact(self, caller, event):
        if self.widget_object is None:
            return
        transform = vtkTransform()
        self.widget.GetTransform(transform)
        matrix = np.array(
            [[transform.GetMatrix().GetElement(i, j) for j in range(4)] for i in range(4)]
        )
        self.transformed.emit(self.widget_object, matrix, self.gesture_key)

    def _end(self, caller, event):
        self._interact(caller, event)
        self.dragging = False
        self.drag_finished.emit()

    def clear_widget(self):
        if self.widget is not None:
            self.widget.Off()
            self.widget.SetInteractor(None)
        self.widget = None
        self.widget_object = None
        self.dragging = False

    def fit_all(self):
        actors = [
            a for a in (*self.viewport.actors.values(), *self.actors.values()) if a.GetVisibility()
        ]
        if not actors:
            return
        bounds = np.asarray([a.bounds for a in actors])
        focused = tuple(
            value
            for axis in range(3)
            for value in (bounds[:, 2 * axis].min(), bounds[:, 2 * axis + 1].max())
        )
        self.viewport.plotter.renderer.view_isometric()
        self.viewport.plotter.renderer.reset_camera(bounds=focused)
        self.viewport.plotter.camera_set = True
        self.viewport.plotter.render()
