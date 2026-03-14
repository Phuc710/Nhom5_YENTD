@echo off
set LAN_IP=192.168.1.7
title HỆ THỐNG GIÁM SÁT CAMERA - STARTING...
echo =============================================================
echo [*] Dang khoi dong toan bo he thong...
echo =============================================================

rem 1. Chay Backend Python tren PORT 8000
echo [*] Dang khoi dong Backend API (Port 8000)...
start "Backend API" cmd /c "cd backend && ..\venv\Scripts\python.exe main.py"

timeout /t 3 /nobreak > nul

rem 2. Chay Frontend PHP tren PORT 8080
echo [*] Dang khoi dong Frontend Web (Port 8080)...
start "Frontend Web" cmd /c "cd frontend && php -S 0.0.0.0:8080 index.php -t ."

echo =============================================================
echo [OK] He thong da san sang!
echo [!] Truy cap Web tai: http://localhost:8080
echo [!] Truy cap Web LAN tai: http://%LAN_IP%:8080
echo [!] API hoat dong tai: http://localhost:8000
echo [!] API LAN tai: http://%LAN_IP%:8000
echo [!] ThingsBoard LAN tai: http://%LAN_IP%:9090
echo [!] MQTT ThingsBoard LAN tai: mqtt://%LAN_IP%:1883
echo =============================================================
timeout /t 5
start http://localhost:8080
pause
