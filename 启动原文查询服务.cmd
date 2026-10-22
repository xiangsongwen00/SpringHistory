@echo off
cd /d "%~dp0myHistorySys"
if not exist ".venv\Scripts\python.exe" (
  echo Missing myHistorySys virtual environment. See myHistorySys\README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" launch_service.py
if errorlevel 1 pause
