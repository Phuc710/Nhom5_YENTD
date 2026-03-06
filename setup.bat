@echo off
echo =============================================================
echo TRAFFIC VIOLATION DETECTION SYSTEM - SETUP
echo =============================================================

rem 1. Tao venv
echo [*] Dang tao venv...
python -m venv venv
if errorlevel 1 (
    echo [!] Loi khi tao venv. Thu voi 'py'...
    py -m venv venv
)

rem 2. Cai dat requirements
echo [*] Dang cai dat thu vien...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r backend/requirements.txt

echo =============================================================
echo DONE! Hay chay: python run.py
echo =============================================================
pause
