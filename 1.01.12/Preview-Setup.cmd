@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preview-Setup.ps1"
if errorlevel 1 (
    pause
    exit /b 1
)
