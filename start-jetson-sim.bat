@echo off
title EO Control - Jetson service (SIM)
cd /d "%~dp0jetson-service"
set "PY=python"
where python >nul 2>nul || set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist .venv (
  "%PY%" -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m eos_service --sim
pause
