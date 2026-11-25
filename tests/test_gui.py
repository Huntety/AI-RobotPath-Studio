"""Real Qt/VTK integration: joint events, FK/actor consistency, model loading and TCP."""

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from robotstudio_ai.gui.main_window import MainWindow
from robotstudio_ai.gui.viewport import geometry_surface
from robotstudio_ai.settings import generic_config_path, load_settings

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot):
    settings, model = load_settings(generic_config_path())
    widget = MainWindow(settings, model)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    yield widget
    widget.close()


def test_joint_slider_spin_fk_and_actors(window, qtbot):
    old = window.fk.tcp.copy()
    window.controls[0].slider.setValue(7500)
    assert window.q[0] == pytest.approx(np.pi / 2)
    assert window.controls[0].spin.value() == pytest.approx(90)
    assert not np.allclose(old, window.fk.tcp)
    window.controls[1].spin.setValue(-30)
    assert window.q[1] == pytest.approx(-np.pi / 6)
    for (name, _), actor in window.viewport.actors.items():
        np.testing.assert_allclose(actor.user_matrix, window.fk.links[name], atol=1e-12)
    # Exercise an actual keyboard event on the numeric input.
    spin = window.controls[2].spin
    spin.setFocus()
    before = window.q[2]
    qtbot.keyClick(spin, Qt.Key.Key_Up)
    assert window.q[2] > before


def test_limits_reject_without_state_mutation(window):
    before = window.q.copy()
    with pytest.raises(ValueError):
        window.set_joint(0, 100)
    np.testing.assert_array_equal(window.q, before)
    window.controls[0].spin.setValue(9999)
    assert window.q[0] == pytest.approx(np.pi)
    window.controls[0].slider.setValue(0)
    assert window.q[0] == pytest.approx(-np.pi)


def test_home_zero_and_tcp_frame_offset(window):
    window.reset_zero()
    np.testing.assert_allclose(window.fk.tcp[:3, 3], [0.85, 0, 0.3], atol=1e-12)
    window.tool_fields[0].setValue(100)
    np.testing.assert_allclose(window.fk.tcp[:3, 3], [0.95, 0, 0.3], atol=1e-12)
    assert "950.000" in window.tcp_position.text()
    window.tool_fields[5].setValue(90)
    np.testing.assert_allclose(
        window.fk.tcp[:3, :3], [[0, -1, 0], [1, 0, 0], [0, 0, 1]], atol=1e-12
    )
    np.testing.assert_allclose(window.viewport.frames["tcp"][0].user_matrix, window.fk.tcp)
    window.reset_home()
    np.testing.assert_allclose(window.q, window.home)


def test_frame_toggle_and_tool_link_selection(window):
    window.axes_toggle.setChecked(False)
    assert all(
        not actor.GetVisibility() for group in window.viewport.frames.values() for actor in group
    )
    window.axes_toggle.setChecked(True)
    window.tool_combo.setCurrentText("base_link")
    np.testing.assert_allclose(window.fk.tcp, np.eye(4), atol=1e-12)
    assert all(
        actor.GetVisibility() for group in window.viewport.frames.values() for actor in group
    )


def test_async_urdf_replaces_only_valid_model(window, qtbot, tmp_path, monkeypatch):
    original = window.model
    bad = tmp_path / "bad.urdf"
    bad.write_text("<robot>", encoding="utf-8")
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    window.load_urdf_async(bad)
    qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert window.model is original
    assert messages
    model_path = generic_config_path().parent / "../robots/generic_6axis/robot.urdf"
    window.load_urdf_async(model_path)
    qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert window.model is not original
    assert not window.model.provenance.hardware_validated
    assert "unverified" in window.model_badge.text()
    np.testing.assert_allclose(window.q, np.zeros(6))


def test_real_stl_obj_scale_origin_and_render(window, qtbot, tmp_path):
    from robotstudio_ai.core.urdf import load_urdf

    mesh = trimesh.creation.box(extents=(100, 50, 25))
    for extension in ("stl", "obj"):
        path = tmp_path / f"block.{extension}"
        mesh.export(path)
        urdf = tmp_path / f"{extension}.urdf"
        urdf.write_text(
            f"""<robot name="mesh_{extension}"><link name="base">
          <visual><origin xyz="0.1 0.2 0.3"/><geometry>
          <mesh filename="block.{extension}" scale="0.001 0.001 0.001"/>
          </geometry></visual></link></robot>""",
            encoding="utf-8",
        )
        model = load_urdf(urdf)
        surface = geometry_surface(model.links["base"].visuals[0])
        np.testing.assert_allclose(surface.center, [0.1, 0.2, 0.3], atol=1e-7)
        np.testing.assert_allclose(
            np.asarray(surface.bounds)[1::2] - np.asarray(surface.bounds)[::2],
            [0.1, 0.05, 0.025],
            atol=1e-7,
        )
        window.load_urdf_async(urdf)
        qtbot.waitUntil(lambda: not window.busy, timeout=15000)
        assert window.model.name == f"mesh_{extension}"
        assert len(window.viewport.actors) == 1


def test_window_screenshot_and_all_joints_visible(window, qtbot):
    qtbot.wait(100)
    window.viewport.fit()
    assert window.viewport.plotter.camera.distance < 3
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    assert window.grab().save(str(output / "phase1-tested-ui.png"))
    for control in window.controls:
        assert control.spin.isVisible()
    image = window.viewport.plotter.screenshot(return_img=True)
    # A render must contain geometry and varying pixel colours rather than a blank surface.
    assert image.shape[0] > 100 and image.shape[1] > 100
    assert np.unique(image.reshape(-1, image.shape[-1]), axis=0).shape[0] > 100
    (output / "render-info.json").write_text(
        json.dumps(
            {
                "window": window.viewport.plotter.render_window.GetClassName(),
                "actors": len(window.viewport.actors),
                "image_size": list(image.shape),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


@pytest.mark.cad_assets
def test_s922_all_six_joint_controls_and_profile_switch(window, qtbot):
    from robotstudio_ai.settings import s922_config_path

    if not s922_config_path().is_file():
        pytest.skip("Run tools/prepare_s922.py locally")
    assert window.model_selector.count() == 2
    window.model_selector.setFocus()
    qtbot.keyClick(window.model_selector, Qt.Key.Key_Down)
    qtbot.waitUntil(lambda: not window.busy, timeout=20000)
    assert window.model.name == "hitbot_s922_cad_reference"
    assert window.model.provenance.joint_coordinates == "cad_relative"
    assert "상대각" in window.model_notice.text()
    assert len(window.viewport.actors) == 13
    for index in range(6):
        window.reset_home()
        baseline = window.fk
        window.controls[index].spin.setValue(15)
        assert window.q[index] == pytest.approx(np.pi / 12)
        assert not np.allclose(window.fk.tcp, baseline.tcp)
        for unchanged in range(index + 1):
            name = "base_link" if unchanged == 0 else f"link{unchanged}"
            np.testing.assert_allclose(window.fk.links[name], baseline.links[name], atol=1e-12)
        for (name, _), actor in window.viewport.actors.items():
            np.testing.assert_allclose(actor.user_matrix, window.fk.links[name], atol=1e-12)
    window.reset_home()
    window.viewport.fit()
    qtbot.wait(50)
    assert window.grab().save("artifacts/s922-tested-ui.png")
    qtbot.keyClick(window.model_selector, Qt.Key.Key_Up)
    qtbot.waitUntil(lambda: not window.busy, timeout=20000)
    assert window.model.provenance.synthetic
    np.testing.assert_allclose(window.q, window.home)
    assert window.tabs.tabText(0) == "관절 조작"
