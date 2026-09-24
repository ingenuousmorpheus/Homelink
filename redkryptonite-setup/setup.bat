@echo off
title HomeLink House Guard Installer
rem Double-click me on any HomeLink guard laptop (elevates automatically)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -NoExit -File \"%~dp0setup.ps1\"'"
