"""Application entry points, including reproducible headless and GUI smoke checks."""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from robotstudio_ai import __version__
from robotstudio_ai.core.kinematics import TreeKinematics
from robotstudio_ai.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RobotStudio AI — offline model workbench")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--headless-check", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings, model = load_settings(args.config)
    except (OSError, ValueError) as error:
        logging.error("Configuration/model error: %s", error)
        return 2
    if args.headless_check:
        fk = TreeKinematics().forward(
            model,
            settings.robot.home_rad,
            settings.robot.tool_link,
            settings.robot.base,
            settings.robot.tool_offset,
        )
        print(
            json.dumps(
                {
                    "model": model.name,
                    "synthetic": model.provenance.synthetic,
                    "joint_coordinates": model.provenance.joint_coordinates,
                    "joints": len(model.active_joints),
                    "tcp_m": fk.tcp[:3, 3].tolist(),
                },
                indent=2,
            )
        )
        return 0
    os.environ["QT_API"] = "pyside6"
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from robotstudio_ai.gui.planning_workbench import PlanningWorkbench

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("RobotStudio AI")
    try:
        window = PlanningWorkbench(settings, model)
    except Exception:
        logging.exception("GUI initialisation failed")
        return 3
    window.show()
    outcome = {"success": True}

    def smoke():
        smoke_errors = []
        window._show_error = lambda message: smoke_errors.append(message)

        def wait_for_io():
            deadline = time.monotonic() + 20
            while window.busy:
                app.processEvents()
                if time.monotonic() > deadline:
                    raise TimeoutError("Scene file operation did not finish")
                time.sleep(0.005)
            if smoke_errors:
                raise RuntimeError(smoke_errors[-1])

        try:
            old_tcp = window.fk.tcp.copy()
            control = window.controls[0]
            control.slider.setValue(min(10000, control.slider.value() + 1000))
            assert not np.allclose(old_tcp, window.fk.tcp)
            for (link, _), actor in window.viewport.actors.items():
                np.testing.assert_allclose(actor.user_matrix, window.fk.links[link], atol=1e-12)
            window.reset_home()
            object_id = window.create_primitive("box")
            token = window.scene.token()
            window.editor.pose.fields[0].setValue(550)
            window.editor.apply_button.click()
            assert window.scene.get_object(object_id).pose.position_m[0] == 0.55
            assert not window.scene.is_current(token)
            window.undo_action.trigger()
            assert window.scene.get_object(object_id).pose.position_m[0] == 0.5
            window.redo_action.trigger()
            assert window.scene.get_object(object_id).pose.position_m[0] == 0.55
            window.delete_selected()
            window.load_demo()
            window.scene_view.fit_all()
            snapshot = window.scene.document
            with tempfile.TemporaryDirectory(prefix="robotstudio-smoke-") as temporary:
                project = Path(temporary) / "scene.rsai"
                window.save_project_path(project)
                wait_for_io()
                assert project.is_file() and not window.scene.dirty
                target = snapshot.objects[1]
                window.scene.remove(target.id)
                window.load_project_path(project)
                wait_for_io()
                assert window.scene.document.objects == snapshot.objects
                assert window.scene.document.robot == snapshot.robot
                assert not window.scene.dirty
            window.analysis.fallback.setChecked(True)
            window.apply_collision_policy()
            window.check_collision()
            wait_for_io()
            assert window.collision_report is not None and window.collision_report.complete
            window.analysis.collision_filter.setChecked(False)
            window.goal_from_current()
            window.solve_ik()
            wait_for_io()
            assert window.ik_result is not None and window.ik_result.success
            window.capture_edge_start()
            window.check_edge()
            wait_for_io()
            assert window.edge_report is not None and window.edge_report.complete
            window.tabs.setCurrentIndex(3)
            app.processEvents()
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot.resolve())):
                    raise RuntimeError("Screenshot save failed")
            outcome.update(
                version=__version__,
                model=model.name,
                joint_coordinates=model.provenance.joint_coordinates,
                actors=len(window.viewport.actors),
                scene_objects=len(window.scene.document.objects),
                scene_roundtrip=True,
                scene_edit_undo_redo=True,
                ik_solved=True,
                collision_complete=True,
                edge_complete=True,
                tcp_m=window.fk.tcp[:3, 3].tolist(),
                render_window=window.viewport.plotter.render_window.GetClassName(),
            )
        except Exception as error:
            logging.exception("GUI smoke failed")
            outcome.update(success=False, error=str(error))
        finally:
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
            window.scene.mark_saved()
            window.close()
            app.quit()

    if args.smoke_test:
        QTimer.singleShot(1500, smoke)
    result = app.exec()
    return result if outcome["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
