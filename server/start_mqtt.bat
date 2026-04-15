@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM start_mqtt.bat
REM - Start local Mosquitto broker for real runtime:
REM   - MQTT TCP: 1883
REM   - MQTT WebSocket: 9001
REM - Use --check to validate setup only (do not run broker).
REM ============================================================

set "CHECK_ONLY=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"

set "MOSQ_EXE="
if exist "%~dp0mosquitto.exe" set "MOSQ_EXE=%~dp0mosquitto.exe"
if not defined MOSQ_EXE if exist "C:\Program Files\mosquitto\mosquitto.exe" set "MOSQ_EXE=C:\Program Files\mosquitto\mosquitto.exe"
if not defined MOSQ_EXE (
  where mosquitto >nul 2>&1
  if not errorlevel 1 set "MOSQ_EXE=mosquitto"
)

echo ==================================================
echo  TrafficAI MQTT Launcher
echo  Config : %~dp0mosquitto.conf
echo  Ports  : 1883 (MQTT), 9001 (WebSocket)
echo ==================================================
echo.

if not exist "%~dp0mosquitto.conf" (
  echo [ERROR] Missing mosquitto.conf in server folder.
  exit /b 1
)

if not defined MOSQ_EXE (
  echo [ERROR] Mosquitto executable not found.
  echo         Install Mosquitto then run again.
  echo         Download: https://mosquitto.org/download/
  echo         Or use  : winget install EclipseFoundation.Mosquitto
  exit /b 1
)

echo [OK] Mosquitto executable: %MOSQ_EXE%

if "%CHECK_ONLY%"=="1" (
  echo [CHECK] MQTT prerequisites are ready.
  exit /b 0
)

echo.
echo [RUN] Starting Mosquitto broker...
echo.
"%MOSQ_EXE%" -c "%~dp0mosquitto.conf" -v
exit /b %ERRORLEVEL%
