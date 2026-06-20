@echo off
cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo Python environment not found. Please run setup_ai_backend.bat first.
    pause
    exit /b 1
)

echo Starting Study Planner AI on http://127.0.0.1:8000
"%PYTHON_EXE%" ai_backend\main.py --host 127.0.0.1 --port 8000
