"""Application entry points, including reproducible headless and GUI smoke checks."""

import argparse
import json
import logging
import os
import sys
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

    from robotstudio_ai.gui.workbench import SceneWorkbench

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("RobotStudio AI")
    try:
        window = SceneWorkbench(settings, model)
    except Exception:
        logging.exception("GUI initialisation failed")
        return 3
    window.show()
    outcome = {"success": True}

    def smoke():
        try:
            old_tcp = window.fk.tcp.copy()
            control = window.controls[0]
            control.slider.setValue(min(10000, control.slider.value() + 1000))
            assert not np.allclose(old_tcp, window.fk.tcp)
            for (link, _), actor in window.viewport.actors.items():
                np.testing.assert_allclose(actor.user_matrix, window.fk.links[link], atol=1e-12)
            window.reset_home()
            window.load_demo()
            window.scene_view.fit_all()
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
