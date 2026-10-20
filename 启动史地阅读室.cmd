@echo off
cd /d "%~dp0"
if not exist "reader\.venv\Scripts\pythonw.exe" (
  echo Reader is not installed. See README.md.
  pause
  exit /b 1
)
start "" "reader\.venv\Scripts\pythonw.exe" "reader\launch_reader.py"
