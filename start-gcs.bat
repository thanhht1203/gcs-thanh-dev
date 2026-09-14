@echo off
title EO Control - GCS Windows
cd /d "%~dp0gcs"
if not exist node_modules (
  npm install
)
npm run electron:dev
