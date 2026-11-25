"""Run the frozen GUI from a foreign cwd without a Python/venv search path."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
exe = root / "dist" / "RobotStudioAI" / "RobotStudioAI.exe"
foreign = root / ".cache" / "bundle-check"
foreign.mkdir(parents=True, exist_ok=True)
report = root / "artifacts" / "bundle-smoke.json"
screenshot = root / "artifacts" / "bundle-ui.png"
environment = dict(os.environ)
metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
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
assert outcome.get("version") == metadata["project"]["version"], outcome
local_manifest = root / "models" / "hitbot_s922" / "model.json"
if local_manifest.is_file():
    manifest = json.loads(local_manifest.read_text(encoding="utf-8"))
    assert outcome["model"] == "hitbot_s922_cad_reference", outcome
    assert outcome["joint_coordinates"] == "cad_relative", outcome
    assert outcome["actors"] == sum(len(part["meshes"]) for part in manifest["parts"]), outcome
else:
    assert outcome["actors"] == 10, outcome
assert screenshot.stat().st_size > 10000
print(json.dumps(outcome, indent=2))
