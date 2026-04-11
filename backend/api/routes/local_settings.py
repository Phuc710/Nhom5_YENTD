"""
Local settings routes — manage data/app_settings.json via API.

Cho phép:
  - Đọc toàn bộ settings
  - Đọc/ghi từng section
  - Reload từ disk (hot-reload)
  - Bật/tắt app (enabled flag)
  - Update traffic light timing cho từng PCB/camera
  - Update ALPR thresholds
"""
import asyncio
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.models import MessageResponse
from backend.api.services.local_settings_service import LocalSettingsService
from backend.api.dependencies import get_local_settings

router = APIRouter(prefix="/local-settings", tags=["Local Settings"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SectionUpdateRequest(BaseModel):
    data: dict


class TrafficTimingRequest(BaseModel):
    red_ms: int
    yellow_ms: int
    green_ms: int


class AppEnabledRequest(BaseModel):
    enabled: bool


class ALPRUpdateRequest(BaseModel):
    vconf: Optional[float] = None
    pconf: Optional[float] = None
    ocr_thres: Optional[float] = None
    read_plate: Optional[bool] = None
    device: Optional[str] = None
    lang: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="Get all local settings",
    description="Returns full contents of data/app_settings.json (loaded in-memory).",
)
async def get_all_settings(svc: LocalSettingsService = Depends(get_local_settings)):
    return await asyncio.to_thread(svc.get_all)


@router.get(
    "/{section}",
    summary="Get settings section",
    description="Returns a specific top-level section (e.g. 'alpr', 'mqtt', 'traffic_light').",
)
async def get_section(
    section: str,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    data = await asyncio.to_thread(svc.get_section, section)
    if data == {}:
        raise HTTPException(status_code=404, detail=f"Section '{section}' not found.")
    return data


@router.put(
    "/{section}",
    response_model=MessageResponse,
    summary="Update a settings section",
    description="Merge-update a top-level section. Only provided keys are changed.",
)
async def update_section(
    section: str,
    request: SectionUpdateRequest,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    ok = await asyncio.to_thread(svc.update_section, section, request.data)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update settings.")
    return MessageResponse(message=f"Section '{section}' updated and saved.")


@router.post(
    "/reload",
    response_model=MessageResponse,
    summary="Hot-reload settings from disk",
    description="Re-reads data/app_settings.json without restarting the server.",
)
async def reload_settings(svc: LocalSettingsService = Depends(get_local_settings)):
    ok = await asyncio.to_thread(svc.reload)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to reload settings from disk.")
    return MessageResponse(message="Settings reloaded from disk.")


@router.put(
    "/app/enabled",
    response_model=MessageResponse,
    summary="Enable or disable the application",
)
async def set_app_enabled(
    request: AppEnabledRequest,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    await asyncio.to_thread(svc.set_app_enabled, request.enabled)
    state = "enabled" if request.enabled else "disabled"
    return MessageResponse(message=f"Application {state}.")


@router.put(
    "/alpr",
    response_model=MessageResponse,
    summary="Update ALPR settings",
    description="Update detection thresholds. Persisted to app_settings.json.",
)
async def update_alpr(
    request: ALPRUpdateRequest,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return MessageResponse(message="No changes provided.")
    await asyncio.to_thread(svc.update_alpr_config, updates)
    return MessageResponse(message=f"ALPR settings updated: {', '.join(updates.keys())}")


@router.put(
    "/traffic-light/default-timings",
    response_model=MessageResponse,
    summary="Update default traffic light timings",
)
async def update_default_timings(
    request: TrafficTimingRequest,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    await asyncio.to_thread(
        svc.update_section,
        "traffic_light", "default_timings",
        {"red_ms": request.red_ms, "yellow_ms": request.yellow_ms, "green_ms": request.green_ms},
    )
    return MessageResponse(
        message=f"Default timings updated: R={request.red_ms}ms Y={request.yellow_ms}ms G={request.green_ms}ms"
    )


@router.put(
    "/traffic-light/pcb/{device_name}/timings",
    response_model=MessageResponse,
    summary="Update timings for specific PCB device",
    description="Updates timings in local settings. Use /mqtt/traffic-light endpoints to send to PCB immediately.",
)
async def update_pcb_timings(
    device_name: str,
    request: TrafficTimingRequest,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    timings = {"red_ms": request.red_ms, "yellow_ms": request.yellow_ms, "green_ms": request.green_ms}
    await asyncio.to_thread(svc.set_pcb_timings, device_name, timings)
    return MessageResponse(
        message=f"PCB '{device_name}' timings saved: R={request.red_ms}ms Y={request.yellow_ms}ms G={request.green_ms}ms"
    )


@router.get(
    "/cameras/{camera_id}",
    summary="Get per-camera local config",
)
async def get_camera_local_config(
    camera_id: int,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    data = await asyncio.to_thread(svc.get_camera_config, camera_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not in local settings.")
    return data


@router.put(
    "/cameras/{camera_id}/zones",
    response_model=MessageResponse,
    summary="Update detection zones for a camera",
)
async def update_camera_zones(
    camera_id: int,
    request: SectionUpdateRequest,
    svc: LocalSettingsService = Depends(get_local_settings),
):
    detect_zone = request.data.get("detect_zone")
    stop_line = request.data.get("stop_line")
    await asyncio.to_thread(svc.set_camera_zones, camera_id, detect_zone, stop_line)
    return MessageResponse(message=f"Camera {camera_id} zones saved to local settings.")
