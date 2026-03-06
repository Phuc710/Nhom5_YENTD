"""
main.py — FastAPI entry point (refactored OOP)
Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from config.settings import get_settings
from database.supabase_client import init_supabase
from utils.logger import setup_logging, get_logger

# Routers
from api.cameras    import router as cameras_router
from api.violations import router as violations_router
from api.upload     import router as upload_router
from api.finalize   import router as finalize_router
from api.stats      import router as stats_router

# ---- Setup ------------------------------------------------

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + Shutdown lifecycle"""
    logger.info("=" * 60)
    logger.info("🚦  HỆ THỐNG PHÁT HIỆN VI PHẠM GIAO THÔNG")
    logger.info("=" * 60)
    init_supabase()
    logger.info("✅  Supabase đã kết nối")

    # Tạo thư mục uploads
    os.makedirs(f"{settings.upload_dir}/original", exist_ok=True)
    os.makedirs(f"{settings.upload_dir}/detected_plates", exist_ok=True)
    logger.info(f"✅  Uploads: {settings.upload_dir}/")
    logger.info(f"🌐  Docs: http://localhost:{settings.port}/docs")
    logger.info("=" * 60)

    yield

    logger.info("👋  Server đã dừng")


# ---- App --------------------------------------------------

app = FastAPI(
    title="Vi phạm Giao thông — API",
    description="Phát hiện vượt đèn đỏ bằng ESP32-S3-CAM + YOLO AI",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Routers
app.include_router(cameras_router,    prefix="/api")
app.include_router(violations_router, prefix="/api")
app.include_router(upload_router,     prefix="/api", tags=["Upload"])
app.include_router(finalize_router,   prefix="/api", tags=["Finalize"])
app.include_router(stats_router,      prefix="/api", tags=["Stats"])


# ---- Health & Root ----------------------------------------

@app.get("/", tags=["System"])
async def root():
    return {
        "name": "Vi phạm Giao thông API",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"])
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
