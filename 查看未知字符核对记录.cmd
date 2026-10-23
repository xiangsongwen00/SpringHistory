@echo off
if not exist "%~dp0readerTool\.local\unknowns\review.html" (
  echo Report missing. Run readerTool character-inspection commands first.
  pause
  exit /b 1
)
start "" "%~dp0readerTool\.local\unknowns\review.html"
