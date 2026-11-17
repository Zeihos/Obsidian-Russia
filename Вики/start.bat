@echo off
cd /d "%~dp0"
set "OBWIKI_BIND=127.0.0.1"
set "OBWIKI_PORT=8100"
py -3 app.py
if errorlevel 1 python app.py
pause
