"""
Điểm vào FastAPI của backend.
Chạy bằng: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.cameras import router as cameras_router
from api.dashboard import router as dashboard_router
from api.finalize import router as finalize_router
from api.stats import router as stats_router
from api.upload import router as upload_router
from api.violations import router as violations_router
from config.settings import get_settings
from database.supabase_client import init_supabase
from utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Vòng đời khởi động và tắt ứng dụng."""
    logger.info("=" * 60)
    logger.info("HỆ THỐNG GIÁM SÁT VI PHẠM GIAO THÔNG")
    logger.info("=" * 60)

    init_supabase()
    logger.info("Đã kết nối Supabase")
    logger.info("Chế độ Supabase auth: %s", settings.supabase_auth_mode)
    logger.info("CORS origins: %s", ", ".join(settings.cors_origins_list))

    os.makedirs(f"{settings.upload_dir}/original", exist_ok=True)
    os.makedirs(f"{settings.upload_dir}/detected_plates", exist_ok=True)
    logger.info("Thư mục lưu ảnh: %s/", settings.upload_dir)
    logger.info("Tài liệu API: http://localhost:%s/docs", settings.port)
    logger.info("=" * 60)

    yield

    logger.info("Đã dừng backend")


app = FastAPI(
    title="API Giám sát vi phạm giao thông",
    description="Backend xử lý camera ESP32-S3, ThingsBoard và hồ sơ vi phạm giao thông",
    version="1.0.0",
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
app.include_router(upload_router, prefix="/api", tags=["Upload"])
app.include_router(finalize_router, prefix="/api", tags=["Finalize"])
app.include_router(stats_router, prefix="/api", tags=["Stats"])
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])


@app.get("/", tags=["System"])
async def root():
    return {
        "name": "API Giám sát vi phạm giao thông",
        "version": "1.0.0",
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
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
