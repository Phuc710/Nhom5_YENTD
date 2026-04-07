@echo off
title Traffic Monitor

cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m app.main
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m app.main
) else (
    python -m app.main
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo App exited with error code %ERRORLEVEL%
    pause
)
