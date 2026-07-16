@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python virtual environment was not found.
  echo Create it with: py -3.11 -m venv .venv
  pause
  exit /b 1
)

if not exist ".env" (
  echo [INFO] .env was not found. Defaults will start the app in sample data mode.
)

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
endlocal
