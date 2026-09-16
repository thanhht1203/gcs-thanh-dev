@echo off
cd /d "%~dp0.."
set JETSON_HOST=192.168.1.16
set JETSON_USER=thanh
py -3 scripts\deploy-jetson.py %*
