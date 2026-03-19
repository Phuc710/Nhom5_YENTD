@echo off
for /f "tokens=*" %%i in ('powershell -Command "Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi', 'Ethernet' | Select-Object -First 1 -ExpandProperty IPAddress"') do set LAN_IP=%%i
if "%LAN_IP%"=="" set LAN_IP=127.0.0.1

title CAMERA AI SYSTEM - STARTING...
echo =============================================================
echo [*] Dang khoi dong toan bo he thong CAMERA AI...
echo =============================================================

rem 0. Sync shared local config from backend/.env
echo [*] Dang dong bo config frontend + ESP32 tu backend/.env...
.\venv\Scripts\python.exe backend\scripts\sync_local_config.py
if errorlevel 1 (
    echo [X] Dong bo config that bai. Kiem tra backend\.env
    pause
    exit /b 1
)

rem 1. Start Backend API
echo [*] Dang khoi dong Backend API (Port 8000)...
start "Backend API" cmd /c "cd backend && ..\venv\Scripts\python.exe main.py"

timeout /t 3 /nobreak > nul

rem 2. Start Frontend PHP
echo [*] Dang khoi dong Frontend Web (Port 8080)...
start "Frontend Web" cmd /c "cd frontend && php -S 0.0.0.0:8080 index.php -t ."

echo =============================================================
echo [OK] He thong da san sang!
echo [!] Web local: http://localhost:8080
echo [!] Web LAN:   http://%LAN_IP%:8080
echo [!] API local: http://localhost:8000
echo [!] API LAN:   http://%LAN_IP%:8000
echo [!] ThingsBoard LAN: http://%LAN_IP%:9090
echo [!] MQTT TB LAN:     mqtt://%LAN_IP%:1883
echo =============================================================
timeout /t 5
start http://127.0.0.1:8080
pause
