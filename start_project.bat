@echo off
cd /d "%~dp0"

echo Starting Study Planner AI backend...
start "Study Planner AI" /min "%~dp0start_ai_backend.bat"

echo.
echo Open the website in XAMPP:
echo http://localhost/Study_Planner/login.html
echo.
echo Keep the Study Planner AI window open while using upload and chat.
pause
