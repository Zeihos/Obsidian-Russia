@echo off
cd /d "%~dp0"
py -3 manage.py admin
if errorlevel 1 python manage.py admin
pause
