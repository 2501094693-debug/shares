@echo off
cd /d "%~dp0"

set "VENV_PY=%USERPROFILE%\.virtualenvs\Desktop-test\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=python"

echo Stopping old servers...
"%VENV_PY%" "%~dp0scripts\_stop_server.py"
exit /b %ERRORLEVEL%
