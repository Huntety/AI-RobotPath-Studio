"""Check packaged resources from a wheel outside the source import path."""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheels = sorted((root / "dist").glob("robotstudio_ai-*.whl"), key=lambda p: p.stat().st_mtime)
if not wheels:
    raise SystemExit("Build a wheel first: python -m build --wheel --no-isolation")
scratch = root / ".cache" / "wheel-check"
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch) as temporary:
    target = Path(temporary)
    with zipfile.ZipFile(wheels[-1]) as wheel:
        wheel.extractall(target)
    command = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import robotstudio_ai
from robotstudio_ai.settings import load_settings, generic_config_path
from robotstudio_ai.core.kinematics import TreeKinematics
import numpy as np
assert Path(robotstudio_ai.__file__).is_relative_to(sys.argv[1])
assert generic_config_path().is_relative_to(sys.argv[1])
settings, model = load_settings(generic_config_path())
actual = TreeKinematics().forward(model, [0]*6, settings.robot.tool_link)
np.testing.assert_allclose(actual.tcp[:3,3], [.85,0,.30], atol=1e-12)
print('Wheel verified:', robotstudio_ai.__version__, model.name)
"""
    subprocess.run([sys.executable, "-I", "-c", command, str(target)], cwd=target, check=True)
