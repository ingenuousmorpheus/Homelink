@echo off
title HomeLink House Guard
cd /d "%~dp0"

set "HOMELINK_NODE_ID=RedKryptonite"
set "HOMELINK_CAMERA_ROLL=\\REDKRYPTONITE\PixServer\Camera Roll"
set "LOG=%~dp0guard.log"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed. Get it from https://www.python.org/downloads/
    echo IMPORTANT: check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

echo Installing/updating camera server dependencies...
python -m pip install -r camera_requirements.txt --quiet --disable-pip-version-check

:run
echo [%date% %time%] Starting House Guard camera server... >> "%LOG%"
python camera_server.py >> "%LOG%" 2>&1
echo [%date% %time%] camera_server.py exited with code %errorlevel% >> "%LOG%"
timeout /t 5 /nobreak >nul
goto run
