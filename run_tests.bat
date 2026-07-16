@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python virtual environment was not found.
  echo Create it with: py -3.11 -m venv .venv
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pytest -q
endlocal
