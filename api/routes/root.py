"""
Root routes: service info and health check.
"""
import torch
from fastapi import APIRouter, Depends

from api.models import ServiceInfoResponse
from api.services.alpr_service import ALPRService
from api.services.db_service import DBService
from api.services.mqtt_service import MQTTService
from api.dependencies import get_alpr_service, get_db_service, get_mqtt_service

router = APIRouter(tags=["General"])


@router.get(
    "/",
    response_model=ServiceInfoResponse,
    summary="Service information",
)
async def root():
    """Return service info and available endpoints."""
    return ServiceInfoResponse(
        service="TrafficCam ALPR API",
        version="2.0.0",
        endpoints={
            # General
            "GET /": "Service information",
            "GET /health": "Health check (ALPR, DB, MQTT status)",
            "GET /docs": "Swagger UI documentation",
            # ALPR
            "POST /predict/image": "Process single image (resets tracking)",
            "POST /predict/frame": "Process video frame (maintains tracking)",
            "POST /reset": "Reset tracker state",
            "GET /config": "Get runtime configuration",
            "PUT /config": "Update runtime configuration",
            # Streaming
            "POST /stream/start": "Start video stream capture",
            "POST /stream/stop": "Stop video stream",
            "GET /stream/status": "Get stream status",
            "GET /stream/feed": "MJPEG video feed",
            # Database
            "GET /cameras": "List cameras",
            "POST /cameras": "Create camera",
            "GET /violations": "List violations",
            "POST /violations": "Record violation",
            "GET /zones": "List detection zones",
            "GET /settings": "List system settings",
            # MQTT
            "GET /mqtt/status": "MQTT connection status",
            "POST /mqtt/traffic-light/{id}": "Control traffic light",
            "POST /mqtt/display/{id}": "Control 7-segment display",
            "POST /mqtt/camera/{id}/control": "Control ESP32-S3 camera",
        },
    )


@router.get(
    "/health",
    summary="Health check",
    description="Reports status of ALPR models, Supabase DB connection, and MQTT broker.",
)
async def health(
    alpr: ALPRService = Depends(get_alpr_service),
    db: DBService = Depends(get_db_service),
    mqtt: MQTTService = Depends(get_mqtt_service),
):
    """Health check: reports GPU, models, DB, and MQTT status."""
    gpu = torch.cuda.is_available()
    config = alpr.get_config()

    return {
        "status": "ok" if alpr.is_ready else "initializing",
        "gpu_available": gpu,
        "device": config.get("device", "cpu") if config else "unknown",
        "vehicle_model_loaded": alpr.is_ready,
        "plate_model_loaded": alpr.is_ready,
        "ocr_enabled": config.get("read_plate", False) if config else False,
        "supabase_connected": db.is_connected,
        "mqtt_connected": mqtt.is_connected,
        "mqtt_enabled": mqtt.get_status().get("enabled", False),
    }
