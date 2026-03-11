@echo off
cd /d "%~dp0"
echo ================================================
echo  Khoi dong Mosquitto MQTT Broker local
echo  Port: 1883  ^| AI Traffic Control System
echo ================================================
echo.

REM Dung service mac dinh cua Windows neu no dang chay (tranh loi chiem port 1883)
net stop mosquitto 2>nul
echo.

REM Thu cach 1: Mosquitto da cai vao Program Files
if exist "C:\Program Files\mosquitto\mosquitto.exe" (
    echo [OK] Tim thay Mosquitto tai Program Files
    "C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto.conf -v
    goto :end
)

REM Thu cach 2: Mosquitto trong PATH
where mosquitto >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [OK] Tim thay Mosquitto trong PATH
    mosquitto -c mosquitto.conf -v
    goto :end
)

REM Chua cai Mosquitto
echo [LOI] Chua cai Mosquitto!
echo.
echo Cai dat Mosquitto:
echo   1. Tai: https://mosquitto.org/download/
echo   2. Chon: Windows (mosquitto-x.x.x-install-win64.exe)
echo   3. Cai dat -^> tick "Add to PATH"
echo   4. Chay lai file nay
echo.
echo Hoac dung winget:
echo   winget install EclipseFoundation.Mosquitto
echo.
pause
:end