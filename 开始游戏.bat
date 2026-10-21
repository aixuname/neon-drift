@echo off
setlocal
cd /d "%~dp0"
set "TEMP=%~dp0temp"
set "TMP=%~dp0temp"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
if not exist "%~dp0runtime\python\pythonw.exe" (
  echo Missing bundled runtime. Please keep the whole game folder together.
  pause
  exit /b 1
)
start "" "%~dp0runtime\python\pythonw.exe" -B "%~dp0game.py"
exit /b 0
