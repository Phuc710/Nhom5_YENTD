#!/usr/bin/env python3
"""
run.py — Launcher: khởi động Backend (FastAPI) + Frontend (PHP built-in server)
Chạy: python run.py
"""
import subprocess
import sys
import os
import time
import signal
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(ROOT, "backend")
FRONTEND_DIR = os.path.join(ROOT, "frontend")

BACKEND_PORT  = 8000
FRONTEND_PORT = 8080

processes = []


def stream_output(proc, prefix: str):
    """In output của subprocess ra terminal với prefix"""
    for line in iter(proc.stdout.readline, b""):
        print(f"[{prefix}] {line.decode('utf-8', errors='replace').rstrip()}", flush=True)


def start_backend():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0",
         "--port", str(BACKEND_PORT),
         "--reload"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(proc)
    threading.Thread(target=stream_output, args=(proc, "BACKEND"), daemon=True).start()
    return proc


def start_frontend():
    proc = subprocess.Popen(
        ["php", "-S", f"0.0.0.0:{FRONTEND_PORT}"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(proc)
    threading.Thread(target=stream_output, args=(proc, "FRONTEND"), daemon=True).start()
    return proc


def shutdown(signum=None, frame=None):
    print("\n🛑  Đang dừng tất cả services...")
    for p in processes:
        p.terminate()
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("✅  Đã dừng.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 60)
    print("🚦  VI PHẠM GIAO THÔNG MANAGEMENT SYSTEM")
    print("=" * 60)
    print(f"📡  Backend  → http://localhost:{BACKEND_PORT}")
    print(f"📡  API Docs → http://localhost:{BACKEND_PORT}/docs")
    print(f"🌐  Frontend → http://localhost:{FRONTEND_PORT}")
    print("=" * 60)
    print("  Nhấn Ctrl+C để dừng\n")

    be = start_backend()
    time.sleep(2)   # Đợi backend khởi động trước
    fe = start_frontend()

    # Giữ main thread chạy + monitor processes
    while True:
        if be.poll() is not None:
            print("⚠️  Backend đã dừng bất ngờ! (exit code:", be.returncode, ")")
            shutdown()
        if fe.poll() is not None:
            print("⚠️  Frontend đã dừng bất ngờ! (exit code:", fe.returncode, ")")
            shutdown()
        time.sleep(2)
