@echo off
cd /d "%~dp0"
py -3 manage.py backup
if errorlevel 1 python manage.py backup
pause
