"""Run the frozen GUI from a foreign cwd without a Python/venv search path."""

import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
exe = root / "dist" / "RobotStudioAI" / "RobotStudioAI.exe"
foreign = root / ".cache" / "bundle-check"
foreign.mkdir(parents=True, exist_ok=True)
report = root / "artifacts" / "bundle-smoke.json"
screenshot = root / "artifacts" / "bundle-ui.png"
environment = dict(os.environ)
for key in (
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
):
    environment.pop(key, None)
environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = subprocess.SW_HIDE
subprocess.run(
    [str(exe), "--smoke-test", "--screenshot", str(screenshot), "--report", str(report)],
    cwd=foreign,
    env=environment,
    check=True,
    timeout=60,
    startupinfo=startup,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
outcome = json.loads(report.read_text(encoding="utf-8"))
assert outcome["success"] is True, outcome
assert outcome.get("version") == "0.1.0", outcome
assert outcome["actors"] == 10, outcome
assert screenshot.stat().st_size > 10000
print(json.dumps(outcome, indent=2))
