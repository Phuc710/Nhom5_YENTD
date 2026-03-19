"""Điểm vào FastAPI của backend giám sát vi phạm giao thông."""

import asyncio
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.api.cameras import router as cameras_router
from backend.api.dashboard import router as dashboard_router
from backend.api.realtime import router as realtime_router
from backend.api.streams import router as streams_router
from backend.api.violations import router as violations_router
from backend.api.settings import router as settings_router
from backend.config.settings import get_settings
from backend.database.supabase_client import init_supabase
from backend.ml.detector import get_detector
from backend.repositories.camera_repository import CameraRepository
from backend.services.camera_service import CameraService
from backend.services.realtime_service import realtime_service
from backend.services.stream_manager import stream_manager
from backend.utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)
API_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo tài nguyên dùng chung khi app start và giải phóng khi dừng."""
    camera_service = CameraService()
    auto_sync_task: asyncio.Task | None = None
    last_auto_sync_error: str | None = None

    logger.info("=" * 60)
    logger.info("HỆ THỐNG GIÁM SÁT VI PHẠM GIAO THÔNG")
    logger.info("=" * 60)

    realtime_service.bind_loop(asyncio.get_running_loop())
    init_supabase()
    logger.info("Đã kết nối Supabase")
    logger.info("Chế độ xác thực Supabase: %s", settings.supabase_auth_mode)
    logger.info("CORS origins: %s", ", ".join(settings.cors_origins_list))
    logger.info(
        "Cadence runtime: camera_ttl=%ss | thingsboard_sync=%ss | hot_reload=%s",
        settings.camera_status_ttl_seconds,
        settings.thingsboard_auto_sync_interval_seconds,
        settings.hot_reload,
    )

    os.makedirs(f"{settings.upload_dir}/violations", exist_ok=True)
    os.makedirs(f"{settings.upload_dir}/plates", exist_ok=True)
    logger.info("Thư mục lưu ảnh: %s/", settings.upload_dir)

    if settings.ml_preload_on_startup:
        try:
            detector = get_detector()
            logger.info("Đã preload mô hình AI trên %s", detector.device)
        except Exception as exc:
            logger.exception("Preload mô hình AI thất bại, backend vẫn tiếp tục khởi động: %s", exc)

    async def auto_sync_devices_loop() -> None:
        nonlocal last_auto_sync_error
        interval = max(5, int(settings.thingsboard_auto_sync_interval_seconds))
        while True:
            await asyncio.sleep(interval)
            try:
                summary = await camera_service.sync_devices_from_thingsboard()
                if last_auto_sync_error is not None:
                    logger.info("Tự động đồng bộ ThingsBoard đã khôi phục")
                    last_auto_sync_error = None
                if summary["scanned"]:
                    logger.info(
                        "ThingsBoard auto-sync | scanned=%s | created=%s | updated=%s",
                        summary["scanned"],
                        summary["created"],
                        summary["updated"],
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                if error_text != last_auto_sync_error:
                    logger.warning("Tự động đồng bộ ThingsBoard không sẵn dụng: %s", error_text)
                    last_auto_sync_error = error_text

    if settings.thingsboard_auto_sync_on_startup:
        try:
            summary = await camera_service.sync_devices_from_thingsboard()
            logger.info(
                "🤝 Startup auto-sync thiết bị | scanned=%s | created=%s | updated=%s",
                summary["scanned"],
                summary["created"],
                summary["updated"],
            )
        except Exception as exc:
            logger.warning("ThingsBoard startup auto-sync unavailable: %s", exc)

    # Khởi động Stream Workers cho tất cả camera
    try:
        await stream_manager.start_all()
    except Exception as exc:
        logger.warning("⚠️ Không thể khởi động StreamManager: %s", exc)

    if settings.thingsboard_auto_sync_interval_seconds > 0:
        auto_sync_task = asyncio.create_task(auto_sync_devices_loop(), name="thingsboard_auto_sync")

    public_api_url = settings.public_api_url or f"http://localhost:{settings.port}"
    logger.info("Tài liệu API: %s/docs", public_api_url.rstrip("/"))

    logger.info("=" * 60)

    yield

    logger.info("Đang dừng StreamManager...")
    if auto_sync_task:
        auto_sync_task.cancel()
        try:
            await auto_sync_task
        except asyncio.CancelledError:
            pass
    await stream_manager.stop_all()
    await camera_service.close()
    logger.info("Backend đã dừng hoàn toàn")


app = FastAPI(
    title="API Giám sát vi phạm giao thông",
    description="Backend xử lý camera ESP32-S3, ThingsBoard và hồ sơ vi phạm giao thông",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host if request.client else "Unknown"
    
    # Bỏ qua log cho các endpoint không quan trọng hoặc quá nhiều
    noisy_prefixes = (
        "/api/ws/stream",
        "/api/realtime/stream",
        "/uploads/",
    )
    noisy_suffixes = ("/stream", "/live-view/sse")
    noisy_get_patterns = (
        r"^/health$",
        r"^/api/cameras$",
        r"^/api/cameras/\d+$",
        r"^/api/cameras/\d+/zones$",
        r"^/api/violations/recent$",
    )

    if (
        request.method == "OPTIONS"
        or request.url.path.startswith(noisy_prefixes)
        or request.url.path.endswith(noisy_suffixes)
        or (request.method == "GET" and any(re.match(pattern, request.url.path) for pattern in noisy_get_patterns))
    ):
        return await call_next(request)
        
    logger.info(f"🚀 YÊU CẦU ĐẾN | {request.method: <6} | {request.url.path} | IP: {client_ip}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        status_code = response.status_code
        if status_code < 400:
            logger.info(f"✅ PHẢN HỒI ĐI | {request.method: <6} | {request.url.path} | HTTP {status_code} | {process_time:.2f}ms")
        else:
            logger.error(f"❌ LỖI XỬ LÝ  | {request.method: <6} | {request.url.path} | HTTP {status_code} | {process_time:.2f}ms")
            
        return response
    except Exception as exc:
        process_time = (time.time() - start_time) * 1000
        logger.exception(f"💥 LỖI HỆ THỐNG | {request.method: <6} | {request.url.path} | LỖI HỆ THỐNG | {process_time:.2f}ms")
        raise


app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Centralized API Router
api_router = APIRouter(prefix="/api")
api_router.include_router(cameras_router)
api_router.include_router(violations_router)
api_router.include_router(dashboard_router)
api_router.include_router(realtime_router)
api_router.include_router(streams_router)
api_router.include_router(settings_router)

app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"❌ LỖI XỬ LÝ  | {request.method: <6} | {request.url.path} | HTTP 422 | ValidationError: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.get("/", tags=["System"])
async def root():
    return {
        "name": "API Giám sát vi phạm giao thông",
        "version": API_VERSION,
        "status": "online",
        "docs": "/docs",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"])
async def health():
    audit = stream_manager.audit_cameras()
    repo = CameraRepository()
    cameras = repo.get_all()
    workers = stream_manager.status().get("workers") or []
    worker_map = {
        int(worker["camera_id"]): worker
        for worker in workers
        if worker.get("camera_id") is not None
    }
    devices_by_mac = []
    for camera in cameras:
        camera_id = camera.get("camera_id")
        if camera_id is None:
            continue
        worker = worker_map.get(int(camera_id), {})
        devices_by_mac.append(
            {
                "mac_address": camera.get("mac_address") or "unknown",
                "camera_name": camera.get("camera_name") or camera.get("device_name") or camera.get("tb_device_name"),
                "ip_address": camera.get("ip_address"),
                "stream_url": camera.get("stream_url"),
                "online": bool(camera.get("online")),
                "stream_running": bool(worker.get("running")),
                "stream_connected": bool(worker.get("connected")),
                "last_seen_at": camera.get("last_seen_at"),
                "last_boot_at": camera.get("last_boot_at"),
            }
        )
    devices_by_mac.sort(key=lambda item: str(item.get("mac_address") or ""))

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "supabase_auth_mode": settings.supabase_auth_mode,
        "cors_origins": settings.cors_origins_list,
        "public_api_url": settings.public_api_url or None,
        "camera_audit": {
            "total": audit["total"],
            "ready": len(audit["ready"]),
            "skipped": len(audit["skipped"]),
        },
        "devices_by_mac": devices_by_mac,
    }


if __name__ == "__main__":
    backend_dir = str(Path(__file__).resolve().parent)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.hot_reload,
        reload_dirs=[backend_dir] if settings.hot_reload else None,
        reload_excludes=["logs/*", "backend/uploads/*", ".pio/*", "frontend/*", "database/*", "detected_plates/*"] if settings.hot_reload else None,
        log_level=settings.log_level.lower(),
    )
