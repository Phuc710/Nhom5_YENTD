@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM start_frontend.bat
REM - Open dashboard pages served by FastAPI backend.
REM - This does not start backend; run start_server.bat first.
REM ============================================================

set "BASE_URL=http://127.0.0.1:5050"
if not "%~1"=="" set "BASE_URL=%~1"

echo ==================================================
echo  TrafficAI Frontend Launcher
echo ==================================================
echo [INFO] Opening pages from: %BASE_URL%
echo.
echo   Dashboard: %BASE_URL%/main
echo   Login    : %BASE_URL%/login
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%BASE_URL%/login'" >nul 2>&1
ping 127.0.0.1 -n 2 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%BASE_URL%/main'" >nul 2>&1

echo [DONE] Browser tabs opened.
exit /b 0
