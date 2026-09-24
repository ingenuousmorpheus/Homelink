@echo off
title HomeLink App Server
rem Serves the built HomeLink app so any device on your Tailscale
rem network can open it at http://100.107.136.88:8080
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed on this PC.
    pause
    exit /b 1
)

if not exist dist\index.html (
    echo App not built yet - run "npm run build" first.
    pause
    exit /b 1
)

echo ==============================================
echo   HOMELINK APP IS SERVING
echo   On your phone (Tailscale on) open:
echo   http://100.107.136.88:8080
echo ==============================================
python serve_app.py
pause
