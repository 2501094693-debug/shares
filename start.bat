@echo off
cd /d "%~dp0"

set "VENV_PY=%USERPROFILE%\.virtualenvs\Desktop-test\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=python"

echo Using: %VENV_PY%

echo Stopping old servers first...
"%VENV_PY%" "%~dp0scripts\_stop_server.py"
if errorlevel 1 (
  echo WARNING: failed to fully free port 5000; continuing anyway.
)

echo Installing dependencies...
"%VENV_PY%" -m pip install -r requirements.txt
echo.
echo Starting FastAPI server at http://127.0.0.1:5000
cd backend
"%VENV_PY%" app.py
