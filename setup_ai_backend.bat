@echo off
cd /d "%~dp0"

set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

if exist "%PYTHON_EXE%" goto found_python

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto found_python
)

echo Python was not found. Install Python 3.12 or use the bundled Codex runtime to create .venv.
pause
exit /b 1

:found_python
if not exist ".venv\Scripts\python.exe" (
    "%PYTHON_EXE%" -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r ai_backend\requirements.txt

echo AI backend setup complete.
pause
