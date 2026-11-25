# PyInstaller onedir build. Run with the shared Python/test environment.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
skip = ("pyvista.examples", "pyvista.ext", "pyvista.jupyter", "pyvista.trame", "pyvista.conftest")
hidden = collect_submodules("pyvista", filter=lambda name: not name.startswith(skip))
datas = collect_data_files("robotstudio_ai") + collect_data_files("pyvista")
for name in ("numpy", "scipy", "pydantic", "pydantic_core", "PyYAML", "PySide6",
             "PySide6_Addons", "PySide6_Essentials", "shiboken6", "pyvista", "pyvistaqt",
             "vtk", "trimesh", "matplotlib", "QtPy"):
    datas += copy_metadata(name)
datas += [(str(root / "docs" / "user_manual.md"), "docs")]
datas += [(str(root / "docs" / "third_party.md"), "docs")]

a = Analysis(
    [str(root / "main.py")], pathex=[str(root / "src")],
    binaries=[], datas=datas, hiddenimports=hidden,
    excludes=["torch", "torchvision", "cv2", "pytest", "IPython", "tkinter", "pandas", "sympy",
              "trame", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtWebEngineQuick", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RobotStudioAI",
          debug=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="RobotStudioAI")
