@echo off
setlocal
cd /d "%~dp0"
if exist "..\Scripts\pythonw.exe" (
  start "" "..\Scripts\pythonw.exe" "%~dp0main.py"
) else (
  echo Python/test shared environment was not found. See README.md.
  pause
)
