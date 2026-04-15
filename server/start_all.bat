@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM start_all.bat
REM - Orchestrate full local real-demo stack on Windows:
REM   1) Mosquitto broker
REM   2) FastAPI backend
REM   3) AI service
REM   4) Open dashboard URLs
REM - Uses relative paths inside this project.
REM ============================================================

set "RUN_AI=1"
if /I "%~1"=="--no-ai" set "RUN_AI=0"

echo ==================================================
echo  TrafficAI Full Stack Starter (Windows)
echo ==================================================
echo.

echo [STEP] Preflight checks...
call "%~dp0start_mqtt.bat" --check
if errorlevel 1 (
  echo [ERROR] MQTT preflight failed.
  exit /b 1
)

call "%~dp0start_server.bat" --check
if errorlevel 1 (
  echo [ERROR] Backend preflight failed.
  exit /b 1
)

if "%RUN_AI%"=="1" (
  call "%~dp0start_ai.bat" --check
  if errorlevel 1 (
    echo [ERROR] AI preflight failed.
    exit /b 1
  )
)

echo [OK] All preflight checks passed.
echo.

echo [STEP] Starting MQTT broker...
start "TrafficAI MQTT" "%~dp0start_mqtt.bat"
timeout /t 2 /nobreak >nul

echo [STEP] Starting FastAPI backend...
start "TrafficAI Backend" "%~dp0start_server.bat"
timeout /t 2 /nobreak >nul

if /I "%RUN_AI%"=="1" goto start_ai
echo [INFO] AI service skipped (--no-ai).
goto open_frontend

:start_ai
echo [STEP] Starting AI service...
start "TrafficAI AI Service" "%~dp0start_ai.bat"
timeout /t 2 /nobreak >nul

:open_frontend

echo [STEP] Opening frontend...
call "%~dp0start_frontend.bat"

echo.
echo ==================================================
echo  Stack started.
echo  URLs:
echo   - Health   : http://127.0.0.1:5050/api/health
echo   - Login    : http://127.0.0.1:5050/login
echo   - Dashboard: http://127.0.0.1:5050/main
echo ==================================================
echo.
echo [TIP] Close each service window to stop that service.
exit /b 0
