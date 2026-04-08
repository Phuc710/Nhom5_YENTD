"""
FastAPI application factory.

- Registers all routers (ALPR, DB, MQTT, Stream)
- Sets up CORS for frontend integration
- Uses lifespan to load/unload models, connect DB and MQTT
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import alpr_service, stream_manager, db_service, mqtt_service, local_settings, image_service

# Phase 1 routes — ALPR & Streaming
from api.routes.root import router as root_router
from api.routes.predict import router as predict_router
from api.routes.predict import reset_router
from api.routes.stream import router as stream_router
from api.routes.config import router as config_router

# Phase 2 routes — Database, MQTT, Settings
from api.routes.cameras import router as cameras_router
from api.routes.violations import router as violations_router
from api.routes.zones import router as zones_router
from api.routes.mqtt import router as mqtt_router
from api.routes.settings import router as settings_router
from api.routes.local_settings import router as local_settings_router
from api.routes.evidence import router as evidence_router

logger = logging.getLogger("trafficcam")


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models, connect DB and MQTT on startup; release on shutdown."""

    # 0. Local settings FIRST — fast, no network, needed by all services
    logger.info("Loading local settings from data/app_settings.json...")
    local_settings.load()
    logger.info("Local settings loaded.")

    # 1. ALPR models
    logger.info("Starting TrafficCam API — loading models...")
    alpr_service.startup()
    stream_manager.set_alpr_service(alpr_service)
    logger.info("ALPR models loaded.")


    # 2. Supabase DB
    logger.info("Connecting to Supabase...")
    db_service.startup()

    # 3. Image Service — needs Supabase client + local settings for WebP config
    logger.info("Starting ImageService (WebP + Supabase Storage)...")
    supabase_client = db_service._client  # shared client
    image_service.startup(supabase_client=supabase_client, local_settings=local_settings)

    # 4. MQTT
    logger.info("Starting MQTT client...")
    mqtt_service.startup()

    logger.info("TrafficCam API is ready.")
    yield

    # Shutdown
    logger.info("Shutting down TrafficCam API...")
    stream_manager.stop()
    mqtt_service.shutdown()
    db_service.shutdown()
    alpr_service.shutdown()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrafficCam ALPR API",
    description=(
        "AI-powered traffic surveillance API.\n\n"
        "**Core**: Vehicle detection, tracking, license plate OCR, MJPEG streaming.\n\n"
        "**Database**: Supabase PostgreSQL — cameras, violations, detection zones, system settings.\n\n"
        "**IoT**: MQTT control for ESP32-S3 cameras, traffic lights, 7-segment displays.\n\n"
        "**Input**: Webcam, RTSP, ESP32-S3 HTTP MJPEG, video files, image upload."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for development; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 1 routers — ALPR & Streaming
app.include_router(root_router)
app.include_router(predict_router)
app.include_router(reset_router)
app.include_router(stream_router)
app.include_router(config_router)

# Phase 2 routers — Database, MQTT, Settings
app.include_router(cameras_router)
app.include_router(violations_router)
app.include_router(zones_router)
app.include_router(mqtt_router)
app.include_router(settings_router)
app.include_router(local_settings_router)
app.include_router(evidence_router)
