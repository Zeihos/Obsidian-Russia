@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ not found. Install Python from python.org and add it to PATH.
  pause
  exit /b 1
)
start "OBSIDIAN RUSSIA SERVER" cmd /k "python server.py"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8080/"
