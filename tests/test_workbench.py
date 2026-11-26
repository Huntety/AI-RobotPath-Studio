"""Real Qt/VTK Phase 2 editing, history, picking and portable project integration."""

from pathlib import Path

import numpy as np
import pytest
import trimesh
from PySide6.QtWidgets import QMessageBox
from vtkmodules.vtkCommonTransforms import vtkTransform

from robotstudio_ai.core.project_io import SceneProject, save_project
from robotstudio_ai.core.schema import Pose
from robotstudio_ai.core.transforms import transform
from robotstudio_ai.gui.workbench import SceneWorkbench
from robotstudio_ai.settings import generic_config_path, load_settings, s922_config_path

pytestmark = pytest.mark.gui


@pytest.fixture
def workbench(qtbot, tmp_path, monkeypatch):
    settings, model = load_settings(generic_config_path())
    window = SceneWorkbench(settings, model, cache_dir=tmp_path / "cache")

    def before_close(widget):
        qtbot.waitUntil(lambda: not widget.busy, timeout=30000)
        widget.scene.mark_saved()

    qtbot.addWidget(window, before_close_func=before_close)
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    window.test_errors = errors
    window.show()
    qtbot.waitExposed(window)
    yield window


def test_create_edit_every_shape_and_flags(workbench):
    w = workbench
    for kind in ("box", "cylinder", "sphere", "frame"):
        object_id = w.create_primitive(kind)
        assert str(object_id) in w.scene_view.actors
        assert w.scene_view.widget is not None
    assert len(w.scene.document.objects) == 4
    w.select_item(str(w.scene.document.objects[0].id))
    token = w.scene.token()
    w.editor.name.setText("제품 A")
    w.editor.kind.setCurrentIndex(w.editor.kind.findData("workpiece"))
    w.editor.pose.fields[0].setValue(640)
    w.editor.pose.fields[5].setValue(30)
    w.editor.size_fields[0].setValue(200)
    w.editor.mass.setValue(2.5)
    w.editor.collision.setChecked(False)
    w.editor.fixed.setChecked(False)
    w.editor.target.setChecked(True)
    w.editor.properties.setPlainText('{"batch": 7}')
    w.editor.apply_button.click()
    obj = w.scene.get_object(w.selected_id)
    assert obj.name == "제품 A" and obj.kind == "workpiece"
    assert obj.mass_kg == 2.5 and not obj.collision_enabled and not obj.fixed and obj.task_target
    assert obj.shape.size_m[0] == pytest.approx(0.2)
    assert obj.properties == {"batch": 7}
    assert not w.scene.is_current(token)
    np.testing.assert_allclose(
        w.scene_view.actors[str(obj.id)].user_matrix,
        transform((0.64, 0, 0.05), (0, 0, np.pi / 6)),
        atol=1e-12,
    )
    assert not w.test_errors


def test_duplicate_delete_undo_redo_and_failed_edit(workbench):
    w = workbench
    original = w.create_primitive("box")
    w.duplicate_selected()
    clone = w.selected_id
    assert clone != str(original) and len(w.scene.document.objects) == 2
    w.delete_selected()
    assert len(w.scene.document.objects) == 1
    w.undo_action.trigger()
    assert len(w.scene.document.objects) == 2
    w.redo_action.trigger()
    assert len(w.scene.document.objects) == 1
    w.select_item(str(original))
    before = w.scene.document
    w.editor.properties.setPlainText("{")
    w.editor.apply_button.click()
    assert w.scene.document == before
    assert w.test_errors


def test_parent_base_tool_and_visibility_follow_same_scene(workbench):
    w = workbench
    parent_id = w.create_primitive("box")
    child_id = w.create_primitive("sphere")
    child = w.scene.get_object(child_id)
    w.scene.update_object(
        child.model_copy(
            update={"parent_frame": str(parent_id), "pose": Pose(position_m=(0.2, 0, 0))}
        )
    )
    np.testing.assert_allclose(
        w.scene_view.actors[str(child_id)].user_matrix[:3, 3], [0.7, 0, 0.05]
    )
    parent = w.scene.get_object(parent_id)
    w.scene.update_object(parent.model_copy(update={"visible": False}))
    assert not w.scene_view.actors[str(parent_id)].GetVisibility()
    assert not w.scene_view.actors[str(child_id)].GetVisibility()
    w.scene.undo()
    w.scene.update_object(child.model_copy(update={"parent_frame": "robot_tool", "pose": Pose()}))
    w.set_joint(0, 0.3)
    np.testing.assert_allclose(w.scene_view.actors[str(child_id)].user_matrix, w.fk.tcp, atol=1e-12)
    w.select_item("robot")
    w.editor.pose.fields[2].setValue(400)
    w.editor.apply_button.click()
    assert w.scene.document.robot.base.position_m == (0, 0, 0.4)
    np.testing.assert_allclose(w.scene_view.actors[str(child_id)].user_matrix, w.fk.tcp, atol=1e-12)
    w.scene.undo()
    assert w.base.position_m == (0, 0, 0)
    assert not w.test_errors


def test_picker_and_real_vtk_widget_transform_transaction(workbench):
    w = workbench
    object_id = w.create_primitive("box")
    obj = w.scene.get_object(object_id)
    w.scene.update_object(obj.model_copy(update={"pose": Pose(position_m=(0.6, -0.3, 0.1))}))
    w.manipulate.setChecked(False)
    w.scene_view.fit_all()
    renderer = w.viewport.plotter.renderer
    renderer.SetWorldPoint(0.6, -0.3, 0.1, 1)
    renderer.WorldToDisplay()
    x, y, _ = renderer.GetDisplayPoint()
    w.select_item("")
    assert w.scene_view.pick_at(round(x), round(y)) == str(object_id)
    assert w.selected_id == str(object_id)
    w.manipulate.setChecked(True)
    widget = w.scene_view.widget
    assert not widget.GetScalingEnabled() and widget.GetRotationEnabled()
    before = w.scene.get_object(object_id).pose
    widget.InvokeEvent("StartInteractionEvent")
    for x in (0.7, 0.8):
        move = vtkTransform()
        move.SetMatrix(transform((x, -0.2, 0.12), (0, 0, 0.4)).ravel())
        widget.SetTransform(move)
        widget.InvokeEvent("InteractionEvent")
    widget.InvokeEvent("EndInteractionEvent")
    np.testing.assert_allclose(
        w.scene_view.actors[str(object_id)].user_matrix,
        transform((0.8, -0.2, 0.12), (0, 0, 0.4)),
        atol=1e-10,
    )
    w.scene.undo()
    assert w.scene.get_object(object_id).pose == before
    w.scene.redo()
    assert w.scene.get_object(object_id).pose.position_m[0] == pytest.approx(0.8)


def test_native_middle_mouse_drag_moves_selected_object(workbench, qtbot):
    w = workbench
    object_id = w.create_primitive("box")
    obj = w.scene.get_object(object_id)
    w.scene.update_object(obj.model_copy(update={"pose": Pose(position_m=(0.7, -0.4, 0.15))}))
    w.scene_view.fit_all()
    qtbot.wait(50)
    renderer = w.viewport.plotter.renderer
    renderer.SetWorldPoint(0.7, -0.4, 0.15, 1)
    renderer.WorldToDisplay()
    x, y, _ = renderer.GetDisplayPoint()
    before = w.scene.get_object(object_id).pose
    interactor = w.viewport.plotter.iren.interactor
    interactor.SetEventPosition(round(x), round(y))
    interactor.InvokeEvent("MiddleButtonPressEvent")
    for delta in (10, 20, 35):
        interactor.SetEventPosition(round(x) + delta, round(y) + 10)
        interactor.InvokeEvent("MouseMoveEvent")
    interactor.InvokeEvent("MiddleButtonReleaseEvent")
    assert not w.scene_view.dragging
    assert w.scene.get_object(object_id).pose != before
    w.scene.undo()
    np.testing.assert_allclose(
        w.scene.get_object(object_id).pose.position_m, before.position_m, atol=1e-12
    )


@pytest.mark.parametrize("extension", ["stl", "obj"])
def test_import_save_load_original_removed_and_robot_state(workbench, qtbot, tmp_path, extension):
    w = workbench
    path = tmp_path / f"part.{extension}"
    mesh = trimesh.creation.box(extents=[100, 50, 25])
    mesh.apply_translation([600, -200, 50])
    mesh.export(path)
    w.import_mesh_path(path, "mm")
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    assert len(w.scene.document.objects) == 1
    assert not w.test_errors
    obj = w.scene.document.objects[0]
    np.testing.assert_allclose(obj.pose.position_m, [0.6, -0.2, 0.05])
    w.tool_fields[0].setValue(20)
    w.set_joint(0, 0.4)
    before = w.scene.document
    expected_tcp = w.fk.tcp.copy()
    output = tmp_path / "environment.rsai"
    w.save_project_path(output)
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    assert output.is_file() and not w.scene.dirty
    path.unlink()
    Path(before.assets[0].path).unlink()
    w.delete_selected()
    w.reset_home()
    w.load_project_path(output)
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    assert w.scene.document.objects == before.objects
    np.testing.assert_allclose(w.fk.tcp, expected_tcp, atol=1e-12)
    assert not w.scene.dirty and not w.scene.can_undo
    assert str(obj.id) in w.scene_view.actors
    assert not w.test_errors


def test_failed_load_preserves_document_robot_and_camera(workbench, qtbot, tmp_path):
    w = workbench
    w.create_primitive("box")
    before, camera = w.scene.document, w.camera_state()
    malformed = before.model_copy(
        update={
            "robot": before.robot.model_copy(
                update={"joints": before.robot.joints.model_copy(update={"positions": (100,) * 6})}
            )
        }
    )
    path = tmp_path / "invalid.rsai"
    save_project(path, SceneProject(scene=malformed))
    w.load_project_path(path)
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    assert w.scene.document == before
    assert w.camera_state() == camera
    assert w.test_errors


def test_new_scene_unsaved_cancel_and_discard(workbench, monkeypatch):
    w = workbench
    w.create_primitive("sphere")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    w.new_scene_dialog()
    assert len(w.scene.document.objects) == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    w.new_scene_dialog()
    assert not w.scene.document.objects and not w.scene.dirty


@pytest.mark.cad_assets
def test_s922_model_switch_keeps_objects_and_project_roundtrip(workbench, qtbot, tmp_path):
    if not s922_config_path().is_file():
        pytest.skip("Prepare official S922 CAD locally")
    w = workbench
    object_id = w.create_primitive("box")
    w.load_profile_async(s922_config_path())
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    assert w.model.name == "hitbot_s922_cad_reference"
    assert len(w.scene.document.objects) == 1 and str(object_id) in w.scene_view.actors
    assert not w.scene.can_undo
    w.load_demo()
    output = tmp_path / "s922.rsai"
    w.save_project_path(output)
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    w.load_profile_async(generic_config_path())
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    w.load_project_path(output)
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    assert w.model.name == "hitbot_s922_cad_reference"
    assert len(w.scene.document.objects) == 6
    w.scene_view.fit_all()
    w.manipulate.setChecked(False)
    w.grab().save("artifacts/phase2-tested-ui.png")
    assert not w.test_errors
