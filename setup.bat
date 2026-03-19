@echo off
echo =============================================================
echo TRAFFIC VIOLATION DETECTION SYSTEM - SETUP
echo =============================================================

rem 1. Tạo venv
echo [*] Đang tạo môi trường ảo (venv)...
python -m venv venv
if errorlevel 1 (
    echo [!] Lỗi khi tạo venv. Thử lại với lệnh 'py'...
    py -m venv venv
)

rem 2. Cài đặt các thư viện phụ thuộc
echo [*] Đang cài đặt thư viện phần mềm...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r backend/requirements.txt

echo =============================================================
echo HOÀN TẤT! Hãy chạy file 'start_system.bat' để khởi động.
echo =============================================================
pause
