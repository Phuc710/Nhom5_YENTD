"""
MQTT control routes: traffic lights, 7-segment displays, ESP32-S3 cameras.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    MQTTPublishRequest,
    TrafficLightControlRequest,
    DisplayControlRequest,
    CameraControlRequest,
    MQTTStatusResponse,
    MessageResponse,
)
from api.services.mqtt_service import MQTTService
from api.dependencies import get_mqtt_service

router = APIRouter(prefix="/mqtt", tags=["MQTT Control"])


def _require_mqtt(svc: MQTTService):
    """Guard: ensure MQTT is connected."""
    if not svc.is_connected:
        raise HTTPException(
            status_code=503,
            detail="MQTT not connected. Check TRAFFIC_MQTT_ENABLED and broker settings.",
        )


# ------------------------------------------------------------------
# Status
# ------------------------------------------------------------------

@router.get(
    "/status",
    response_model=MQTTStatusResponse,
    summary="MQTT connection status",
)
async def mqtt_status(svc: MQTTService = Depends(get_mqtt_service)):
    return MQTTStatusResponse(**svc.get_status())


# ------------------------------------------------------------------
# Generic publish
# ------------------------------------------------------------------

@router.post(
    "/publish",
    response_model=MessageResponse,
    summary="Publish to MQTT topic",
    description="Send a raw MQTT message to any topic.",
)
async def mqtt_publish(
    request: MQTTPublishRequest,
    svc: MQTTService = Depends(get_mqtt_service),
):
    _require_mqtt(svc)
    ok = svc.publish(request.topic, request.payload, qos=request.qos, retain=request.retain)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to publish MQTT message.")
    return MessageResponse(message=f"Published to {request.topic}")


# ------------------------------------------------------------------
# Traffic Light
# ------------------------------------------------------------------

@router.post(
    "/traffic-light/{light_id}",
    response_model=MessageResponse,
    summary="Control traffic light",
    description="Send state command to a traffic light (red/yellow/green/off/flash_yellow).",
)
async def control_traffic_light(
    light_id: int,
    request: TrafficLightControlRequest,
    svc: MQTTService = Depends(get_mqtt_service),
):
    _require_mqtt(svc)
    ok = svc.control_traffic_light(light_id, request.state, request.duration_s)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send traffic light command.")
    return MessageResponse(message=f"Traffic light {light_id} → {request.state}")


# ------------------------------------------------------------------
# 7-Segment Display
# ------------------------------------------------------------------

@router.post(
    "/display/{display_id}",
    response_model=MessageResponse,
    summary="Control 7-segment display",
    description="Send text to a 7-segment display.",
)
async def control_display(
    display_id: int,
    request: DisplayControlRequest,
    svc: MQTTService = Depends(get_mqtt_service),
):
    _require_mqtt(svc)
    ok = svc.control_display(display_id, request.text, request.brightness)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send display command.")
    return MessageResponse(message=f"Display {display_id} → '{request.text}'")


# ------------------------------------------------------------------
# ESP32-S3 Camera Control
# ------------------------------------------------------------------

@router.post(
    "/camera/{camera_id}/control",
    response_model=MessageResponse,
    summary="Control ESP32-S3 camera",
    description="Send command to ESP32-S3 (restart, rotate, set_resolution, etc.).",
)
async def control_camera(
    camera_id: int,
    request: CameraControlRequest,
    svc: MQTTService = Depends(get_mqtt_service),
):
    _require_mqtt(svc)
    ok = svc.control_camera(camera_id, request.command, request.params)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send camera command.")
    return MessageResponse(message=f"Camera {camera_id} → {request.command}")


# ------------------------------------------------------------------
# Device Telemetry (cached from subscriptions)
# ------------------------------------------------------------------

@router.get(
    "/telemetry",
    summary="Get device telemetry",
    description="Returns cached telemetry data from ESP32-S3 devices.",
)
async def get_telemetry(
    camera_id: Optional[int] = None,
    svc: MQTTService = Depends(get_mqtt_service),
):
    return svc.get_device_telemetry(camera_id)


@router.get(
    "/devices/status",
    summary="Get cached device status",
    description="Returns cached status messages from all MQTT devices.",
)
async def get_device_status(
    camera_id: Optional[int] = None,
    svc: MQTTService = Depends(get_mqtt_service),
):
    return svc.get_device_status_cache(camera_id)
