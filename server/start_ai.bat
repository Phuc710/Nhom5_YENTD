@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM start_ai.bat
REM - Start AI service pipeline (camera -> detect/OCR -> POST /api/violations).
REM - Use --check to validate venv + dependencies only.
REM ============================================================

set "AI_FILE=ai_engine.py"
set "REQ_FILE=requirements.txt"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "CHECK_ONLY=0"

if /I "%~1"=="--check" set "CHECK_ONLY=1"

echo ==================================================
echo  TrafficAI AI Service Launcher
echo  Workspace: %~dp0
echo ==================================================
echo.

if not exist "%AI_FILE%" (
  echo [ERROR] Missing %AI_FILE% in server folder.
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo [ERROR] Python venv not found:
  echo         %VENV_PY%
  echo.
  echo Create venv:
  echo   py -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r %REQ_FILE%
  exit /b 1
)

echo [OK] Interpreter: %VENV_PY%

echo [STEP] Checking AI dependencies...
"%VENV_PY%" -c "import cv2, ultralytics, easyocr, requests" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Missing AI dependencies. Installing from %REQ_FILE%...
  "%VENV_PY%" -m pip install -r "%REQ_FILE%"
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    exit /b 1
  )
)
echo [OK] Dependencies ready.

if "%CHECK_ONLY%"=="1" (
  echo [CHECK] AI service prerequisites are ready.
  exit /b 0
)

echo.
echo [RUN] Starting AI service...
echo       Ctrl+C to stop AI service.
echo.
"%VENV_PY%" "%AI_FILE%"
exit /b %ERRORLEVEL%

