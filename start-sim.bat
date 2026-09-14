@echo off
title EO Control - full SIM
cd /d "%~dp0"
start "EO Jetson SIM" cmd /k "%~dp0start-jetson-sim.bat"
timeout /t 4 /nobreak >nul
start "EO GCS" cmd /k "%~dp0start-gcs.bat"
