@echo off
cd /d "%~dp0"
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting server at http://127.0.0.1:5000
cd backend
python app.py
