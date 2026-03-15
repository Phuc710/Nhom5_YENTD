"""Điểm vào FastAPI của backend giám sát vi phạm giao thông."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.api.cameras import router as cameras_router
from backend.api.dashboard import router as dashboard_router
from backend.api.realtime import router as realtime_router
from backend.api.streams import router as streams_router
from backend.api.violations import router as violations_router
from backend.config.settings import get_settings
from backend.database.supabase_client import init_supabase
from backend.ml.detector import get_detector
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
    logger.info("=" * 60)
    logger.info("HỆ THỐNG GIÁM SÁT VI PHẠM GIAO THÔNG")
    logger.info("=" * 60)

    realtime_service.bind_loop(asyncio.get_running_loop())
    init_supabase()
    logger.info("Đã kết nối Supabase")
    logger.info("Chế độ xác thực Supabase: %s", settings.supabase_auth_mode)
    logger.info("CORS origins: %s", ", ".join(settings.cors_origins_list))

    os.makedirs(f"{settings.upload_dir}/violations", exist_ok=True)
    os.makedirs(f"{settings.upload_dir}/plates", exist_ok=True)
    logger.info("Thư mục lưu ảnh: %s/", settings.upload_dir)

    if settings.ml_preload_on_startup:
        try:
            detector = get_detector()
            logger.info("Đã preload mô hình AI trên %s", detector.device)
        except Exception as exc:
            logger.exception("Preload mô hình AI thất bại, backend vẫn tiếp tục khởi động: %s", exc)

    # Khởi động Stream Workers cho tất cả camera
    try:
        await stream_manager.start_all()
    except Exception as exc:
        logger.warning("⚠️ Không thể khởi động StreamManager: %s", exc)

    public_api_url = settings.public_api_url or f"http://localhost:{settings.port}"
    logger.info("Tài liệu API: %s/docs", public_api_url.rstrip("/"))

    logger.info("=" * 60)

    yield

    logger.info("Đang dừng StreamManager...")
    await stream_manager.stop_all()
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

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(cameras_router, prefix="/api")
app.include_router(violations_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(realtime_router, prefix="/api")
app.include_router(streams_router, prefix="/api", tags=["Streams"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(
        "422 ValidationError %s %s → %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
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
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "supabase_auth_mode": settings.supabase_auth_mode,
        "cors_origins": settings.cors_origins_list,
        "public_api_url": settings.public_api_url or None,
    }


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
