"""Điểm vào FastAPI của backend giám sát vi phạm giao thông."""

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.cameras import router as cameras_router
from api.dashboard import router as dashboard_router
from api.violations import router as violations_router
from config.settings import get_settings
from database.supabase_client import init_supabase
from ml.detector import get_detector
from services.camera_service import CameraService
from utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo tài nguyên dùng chung khi app start và giải phóng khi dừng."""
    logger.info("=" * 60)
    logger.info("HỆ THỐNG GIÁM SÁT VI PHẠM GIAO THÔNG")
    logger.info("=" * 60)

    init_supabase()
    logger.info("Đã kết nối Supabase")
    logger.info("Chế độ xác thực Supabase: %s", settings.supabase_auth_mode)
    logger.info("CORS origins: %s", ", ".join(settings.cors_origins_list))

    os.makedirs(f"{settings.upload_dir}/original", exist_ok=True)
    os.makedirs(f"{settings.upload_dir}/detected_plates", exist_ok=True)
    logger.info("Thư mục lưu ảnh: %s/", settings.upload_dir)

    if settings.ml_preload_on_startup:
        try:
            detector = get_detector()
            logger.info("Đã preload mô hình AI trên %s", detector.device)
        except Exception as exc:
            logger.exception("Preload mô hình AI thất bại, backend vẫn tiếp tục khởi động: %s", exc)

    logger.info("Tài liệu API: http://localhost:%s/docs", settings.port)

    stop_event = asyncio.Event()
    sync_task = None

    async def thingsboard_sync_loop() -> None:
        service = CameraService()
        while not stop_event.is_set():
            try:
                result = await asyncio.to_thread(service.sync_devices_from_thingsboard)
                if result.get("scanned"):
                    logger.info(
                        "ThingsBoard sync nền: quét=%s tạo=%s cập nhật=%s",
                        result.get("scanned"),
                        result.get("created"),
                        result.get("updated"),
                    )
            except Exception as exc:
                logger.error("ThingsBoard sync nền lỗi: %s", exc)

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=max(5, settings.thingsboard_sync_interval_seconds),
                )
            except asyncio.TimeoutError:
                continue

    if settings.thingsboard_sync_enabled:
        sync_task = asyncio.create_task(thingsboard_sync_loop(), name="thingsboard-device-sync")
        logger.info(
            "Bật đồng bộ ThingsBoard định kỳ mỗi %s giây",
            settings.thingsboard_sync_interval_seconds,
        )

    logger.info("=" * 60)

    yield

    stop_event.set()
    if sync_task:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task

    logger.info("Đã dừng backend")


app = FastAPI(
    title="API Giám sát vi phạm giao thông",
    description="Backend xử lý camera ESP32-S3, ThingsBoard và hồ sơ vi phạm giao thông",
    version="1.1.0",
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

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(cameras_router, prefix="/api")
app.include_router(violations_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])


@app.get("/", tags=["System"])
async def root():
    return {
        "name": "API Giám sát vi phạm giao thông",
        "version": "1.1.0",
        "status": "online",
        "docs": "/docs",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "supabase_auth_mode": settings.supabase_auth_mode,
        "cors_origins": settings.cors_origins_list,
        "thingsboard_sync_enabled": settings.thingsboard_sync_enabled,
        "thingsboard_sync_interval_seconds": settings.thingsboard_sync_interval_seconds,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
