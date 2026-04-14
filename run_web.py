"""
run_web.py — Khởi động Traffic Violation Monitor Web Server.

Serve toàn bộ frontend/ (login.html, main.html, index.html) qua FastAPI.
Cùng hệ thống backend với Desktop app: DB, MQTT, AI, streaming.

Chạy:
    python run_web.py                    # port 9000 (mặc định)
    python run_web.py --port 8080        # port khác
    python run_web.py --host 0.0.0.0     # expose toàn LAN
    python run_web.py --reload           # hot-reload (dev)
    python run_web.py --no-ai            # bỏ qua preload AI

Routes:
    /          → redirect → /login
    /login     → frontend/login.html
    /app       → frontend/main.html
    /boot      → frontend/index.html
    /api/...   → FastAPI backend (xem /docs)
    /health    → /api/health alias
    /*.css|js  → frontend/ static assets
"""
import os
import sys
import argparse
from pathlib import Path

# ── Path setup (giống run_app.py) ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

# ── UVI-style logging ─────────────────────────────────────────────────────────
from backend.utils.logger import setup_logging
setup_logging("INFO")

import logging
logger = logging.getLogger("WebLauncher")


def parse_args():
    p = argparse.ArgumentParser(description="Traffic Violation Monitor — Web Server")
    p.add_argument("--host",   default="0.0.0.0",  help="Bind host  (default: 0.0.0.0)")
    p.add_argument("--port",   default=9000, type=int, help="Bind port  (default: 9000)")
    p.add_argument("--reload", action="store_true",  help="Hot-reload (dev only)")
    p.add_argument("--no-ai",  action="store_true",  help="Bỏ qua preload AI models")
    return p.parse_args()


def _add_api_bridges(app):
    """
    Thêm các API alias mà frontend JS gọi nhưng backend chưa expose đúng path.
    Cụ thể: /api/health, /api/login, /api/bootstrap, /api/theme, v.v.
    """
    from fastapi import APIRouter, Depends, Request
    from fastapi.responses import JSONResponse

    bridge = APIRouter(prefix="/api", tags=["Frontend Bridge"])

    # ── /api/health — proxy đến /health ────────────────────────────────────
    @bridge.get("/health", summary="Frontend health check")
    async def api_health(request: Request):
        from backend.api.dependencies import alpr_service, db_service, mqtt_service
        import torch
        try:
            config = alpr_service.get_config() or {}
        except Exception:
            config = {}
        return {
            "ok": True,
            "status": "ok" if alpr_service.is_ready else "initializing",
            "version": "2.0.0",
            "gpu_available": torch.cuda.is_available(),
            "vehicle_model_loaded": alpr_service.is_ready,
            "plate_model_loaded": alpr_service.is_ready,
            "supabase_connected": db_service.is_connected,
            "mqtt": mqtt_service.is_connected,
            "mqtt_connected": mqtt_service.is_connected,
        }

    # ── /api/login — xác thực đơn giản (username/password local) ───────────
    @bridge.post("/login", summary="Frontend login")
    async def api_login(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

        username = (body.get("username") or "").strip().lower()
        password = (body.get("password") or "")

        # Credentials cấu hình trong .env hoặc dùng default admin/admin123
        import os
        valid_user = os.getenv("WEB_USERNAME", "admin").lower()
        valid_pass = os.getenv("WEB_PASSWORD", "admin123")

        if username == valid_user and password == valid_pass:
            import time, hashlib
            token = hashlib.sha256(f"{username}{time.time()}SECRET".encode()).hexdigest()
            return {"ok": True, "token": token, "role": "admin", "username": username}
        return JSONResponse({"ok": False, "error": "Sai tên đăng nhập hoặc mật khẩu"}, status_code=401)

    # ── /api/bootstrap — trạng thái hệ thống tổng hợp ──────────────────────
    @bridge.get("/bootstrap", summary="System bootstrap status")
    async def api_bootstrap():
        from backend.api.dependencies import db_service, mqtt_service
        cameras = []
        try:
            cameras = db_service.list_cameras() or []
        except Exception:
            pass
        return {
            "ok": True,
            "cameras": cameras,
            "mqtt": {"connected": mqtt_service.is_connected},
            "devices": {},  # ESP32 devices — cập nhật nếu cần
        }

    # ── /api/theme — dark mode theme preference ─────────────────────────────
    _theme_store = {"theme": "dark"}

    @bridge.get("/theme", summary="Get theme preference")
    async def get_theme():
        return _theme_store

    @bridge.post("/theme", summary="Set theme preference")
    async def set_theme(request: Request):
        body = await request.json()
        _theme_store["theme"] = body.get("theme", "dark")
        return {"ok": True, **_theme_store}

    # ── /api/device-status — MQTT device cache ──────────────────────────────
    @bridge.get("/device-status", summary="Cached MQTT device status")
    async def device_status():
        from backend.api.dependencies import mqtt_service
        try:
            return mqtt_service.get_device_status_cache()
        except Exception:
            return {}

    # ── /api/update_location — GPS location update (no-op) ─────────────────
    @bridge.post("/update_location", summary="Update GPS location")
    async def update_location(request: Request):
        return {"ok": True}

    # ── /api/laptop_camera/* — webcam laptop pipeline ───────────────────────
    _laptop_cam_state = {"running": False}

    @bridge.get("/laptop_camera/ready")
    async def laptop_cam_ready():
        return {"ok": True, "ready": True}

    @bridge.post("/laptop_camera/start")
    async def laptop_cam_start():
        _laptop_cam_state["running"] = True
        return {"ok": True, "status": "started"}

    @bridge.post("/laptop_camera/stop")
    async def laptop_cam_stop():
        _laptop_cam_state["running"] = False
        return {"ok": True, "status": "stopped"}

    @bridge.get("/laptop_camera/status")
    async def laptop_cam_status():
        return {"ok": True, **_laptop_cam_state}

    @bridge.post("/laptop_camera/snapshot")
    async def laptop_cam_snapshot(request: Request):
        return {"ok": True, "plate": None, "confidence": 0}

    @bridge.post("/plate/scan")
    async def plate_scan(request: Request):
        return {"ok": True, "plate": None, "confidence": 0}

    app.include_router(bridge)
    logger.info("API bridge routes registered under /api/")


def _mount_frontend(app):
    """
    Serve frontend/ HTML pages + static assets.
    HTML: /login, /app, /boot
    Assets: *.css, *.js, images/... (path tương đối từ HTML)
    """
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

    frontend_dir = ROOT / "frontend"
    if not frontend_dir.exists():
        logger.error("frontend/ không tồn tại — web UI disabled")
        return

    web_router = APIRouter(tags=["Web UI"])

    def _html(filename: str, request=None) -> HTMLResponse:
        path = frontend_dir / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"{filename} not found")
        content = path.read_text(encoding="utf-8")
        # Inject API base URL (dùng origin của request để tự động lấy đúng host:port)
        if request is not None:
            base_url = f"{request.url.scheme}://{request.url.netloc}"
        else:
            base_url = ""
        inject = f'<script>window.API_BASE_URL = "{base_url}";</script>'
        content = content.replace("</head>", f"{inject}\n</head>", 1)
        return HTMLResponse(content)

    # ── HTML pages ─────────────────────────────────────────────────────────
    @web_router.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/login")

    @web_router.get("/login",  include_in_schema=False)
    async def login_page(request: Request):
        return _html("login.html", request)

    @web_router.get("/app",    include_in_schema=False)
    async def main_app(request: Request):
        return _html("main.html", request)

    @web_router.get("/boot",   include_in_schema=False)
    async def boot_screen(request: Request):
        return _html("index.html", request)

    # ── Static file fallback — phục vụ CSS/JS/images tại root path ─────────
    # Ví dụ: GET /main.css → frontend/main.css
    @web_router.get("/{filepath:path}", include_in_schema=False)
    async def static_fallback(filepath: str):
        # Bảo vệ path traversal
        safe = (frontend_dir / filepath).resolve()
        if not str(safe).startswith(str(frontend_dir.resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")
        if safe.exists() and safe.is_file():
            return FileResponse(str(safe))
        raise HTTPException(status_code=404, detail=f"Asset not found: {filepath}")

    app.include_router(web_router)
    logger.info("Frontend/%s mounted at routes: /login /app /boot + static fallback", frontend_dir.name)


def main():
    args = parse_args()

    # ── Pre-load AI models ────────────────────────────────────────────────────
    if not args.no_ai:
        try:
            from backend.config.settings import settings
            if settings.ml_enabled:
                logger.info("Pre-loading AI models...")
                from backend.ml.detector import get_detector
                get_detector()
                logger.info("AI models loaded ✅")
        except Exception as exc:
            logger.warning("AI model preload skipped: %s", exc)

    # ── Inject routes vào FastAPI app ─────────────────────────────────────────
    from backend.api.app import app as fastapi_app

    _add_api_bridges(fastapi_app)   # /api/health, /api/login, /api/bootstrap...
    _mount_frontend(fastapi_app)    # /login, /app, /boot, static assets

    # ── Print banner ──────────────────────────────────────────────────────────
    display_host = "localhost" if args.host == "0.0.0.0" else args.host
    logger.info("=" * 62)
    logger.info("🌐  Traffic Violation Monitor — Web Interface")
    logger.info("    ● Login     : http://%s:%d/login",  display_host, args.port)
    logger.info("    ● Dashboard : http://%s:%d/app",    display_host, args.port)
    logger.info("    ● Boot      : http://%s:%d/boot",   display_host, args.port)
    logger.info("    ● API Docs  : http://%s:%d/docs",   display_host, args.port)
    if args.host == "0.0.0.0":
        try:
            import socket
            lan_ip = socket.gethostbyname(socket.gethostname())
            logger.info("    ● LAN       : http://%s:%d/login", lan_ip, args.port)
        except Exception:
            pass
    logger.info("    ● Login: admin / admin123  (đổi qua WEB_USERNAME/WEB_PASSWORD trong .env)")
    logger.info("=" * 62)

    # ── Khởi động Uvicorn ─────────────────────────────────────────────────────
    import uvicorn
    uvicorn.run(
        "backend.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None,
    )


if __name__ == "__main__":
    main()
