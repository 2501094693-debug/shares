@echo off
REM Run AFTER closing PyCharm to remove leftover project .venv lock leftovers.
cd /d "%~dp0.."
if exist ".venv" (
  echo Removing leftover .venv ...
  rmdir /s /q ".venv"
  if exist ".venv" (
    echo Failed: close PyCharm/python first, then rerun this script.
    exit /b 1
  )
  echo Done.
) else (
  echo No leftover .venv found.
)
