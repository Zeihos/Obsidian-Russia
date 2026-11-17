@echo off
cd /d "%~dp0"
py -3.12 --version >nul 2>nul
if not errorlevel 1 (
  py -3.12 dev.py run
) else (
  python dev.py run
)
if errorlevel 1 (
  echo.
  echo Failed to start OBSIDIAN RUSSIA. Python 3.12+ is required.
  pause
)
