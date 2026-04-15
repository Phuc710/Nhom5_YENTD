@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM start_server.bat
REM - Start FastAPI backend (app.py) using local .venv.
REM - Use --check to validate setup only.
REM ============================================================

set "APP_FILE=app.py"
set "REQ_FILE=requirements.txt"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "CHECK_ONLY=0"

if /I "%~1"=="--check" set "CHECK_ONLY=1"

echo ==================================================
echo  AI Traffic FastAPI Server Launcher
echo  Workspace: %~dp0
echo ==================================================
echo.

if not exist "%APP_FILE%" (
  echo [ERROR] Khong tim thay %APP_FILE% trong thu muc server.
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo [ERROR] Khong tim thay Python virtual env:
  echo         %VENV_PY%
  echo.
  echo Tao moi moi truong:
  echo   py -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r %REQ_FILE%
  exit /b 1
)

echo [OK] Interpreter: %VENV_PY%

echo [STEP] Kiem tra cac package bat buoc...
"%VENV_PY%" -c "import fastapi, uvicorn, sqlalchemy, paho.mqtt.client, requests" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Thieu dependency. Dang cai dat tu %REQ_FILE%...
  "%VENV_PY%" -m pip install -r "%REQ_FILE%"
  if errorlevel 1 (
    echo [ERROR] Cai dependency that bai.
    exit /b 1
  )
)
echo [OK] Dependency san sang.

if "%CHECK_ONLY%"=="1" (
  echo [CHECK] Moi thu da san sang. Khong khoi dong server voi tham so --check.
  exit /b 0
)

echo.
echo [RUN] Start FastAPI backend voi dung venv...
echo       Ctrl+C de dung server.
echo.
"%VENV_PY%" "%APP_FILE%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [DONE] Server dung binh thuong.
) else (
  echo [ERROR] Server thoat voi ma loi %EXIT_CODE%.
)

exit /b %EXIT_CODE%
