@echo off
title HomeLink House Guard
cd /d "%~dp0"

set "HOMELINK_CAMERA_ROLL=\\REDKRYPTONITE\PixServer\Camera Roll"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed. Get it from https://www.python.org/downloads/
    echo IMPORTANT: check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

echo Installing/updating camera server dependencies...
python -m pip install -r camera_requirements.txt --quiet

echo Starting House Guard camera server...
python camera_server.py
pause
