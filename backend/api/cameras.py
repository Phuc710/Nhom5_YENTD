"""Camera REST API cho dashboard admin, snapshot, preview va detect upload."""

from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from backend.models.camera import (
    CameraCreate,
    CameraHeartbeat,
    CameraResponse,
    CameraUpdate,
    ProvisionSync,
)
from backend.models.zone import ZoneResponse, ZonesBulkUpdate
from backend.repositories.camera_repository import CameraRepository
from backend.services.realtime_service import realtime_service
from backend.services.camera_service import CameraService
from backend.services.detection_service import DetectionService

router = APIRouter(prefix="/cameras", tags=["Cameras"])
camera_service = CameraService()
detection_service = DetectionService()


def _current_traffic_light_state(camera: dict) -> str:
    light_mode = str(camera.get("light_mode") or "").strip().lower()
    if light_mode in {"red", "yellow", "green"}:
        return light_mode
    return "green"


@router.get("", response_model=List[CameraResponse])
async def list_cameras():
    return camera_service.list_cameras()


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(data: CameraCreate):
    try:
        return camera_service.register_camera(data)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: int):
    try:
        return camera_service.get_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{camera_id}/live-view")
async def get_camera_live_view(camera_id: int):
    """Payload admin cho overlay stream, detect va trang thai camera."""
    try:
        return camera_service.get_live_view(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{camera_id}/stream")
async def proxy_camera_stream(camera_id: int) -> StreamingResponse:
    try:
        return await camera_service.proxy_stream(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.get("/{camera_id}/snapshot")
async def proxy_camera_snapshot(camera_id: int) -> Response:
    try:
        return await camera_service.proxy_snapshot(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.post("/{camera_id}/detect-preview")
async def detect_camera_preview(
    camera_id: int,
    captured_at: str | None = None,
):
    """Lay snapshot moi nhat, detect de admin xem boxing live, khong luu violation."""
    try:
        camera = camera_service.get_camera(camera_id)
        snapshot = await camera_service.proxy_snapshot(camera_id)
        await detection_service.preview_frame(
            camera_id=camera_id,
            image_bytes=snapshot.body,
            captured_at=captured_at,
            traffic_light_state=_current_traffic_light_state(camera),
        )
        return camera_service.get_live_view(camera_id)
    except ValueError as exc:
        message = str(exc)
        if "khong ton tai" in message.lower():
            raise HTTPException(404, message)
        raise HTTPException(400, message)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.post("/{camera_id}/detect-upload")
async def detect_camera_upload(
    camera_id: int,
    image: UploadFile = File(...),
    captured_at: str | None = Form(None),
    location: str | None = Form(None),
    traffic_light_state: str = Form("red"),
):
    """Admin upload 1 anh, detect tat ca BSX trong anh va drop ra tung ket qua."""
    try:
        return await detection_service.process_upload_image(
            camera_id=camera_id,
            image_bytes=await image.read(),
            captured_at=captured_at,
            location=location,
            traffic_light_state=traffic_light_state,
        )
    except ValueError as exc:
        message = str(exc)
        if "khong ton tai" in message.lower():
            raise HTTPException(404, message)
        raise HTTPException(400, message)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, data: CameraUpdate):
    try:
        return camera_service.update_camera(camera_id, data)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{camera_id}/factory-reset")
async def factory_reset_camera(camera_id: int):
    try:
        return camera_service.factory_reset_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Gui lenh factory reset that bai: {exc}")


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int):
    deleted = CameraRepository().delete(camera_id)
    if not deleted:
        raise HTTPException(404, f"Camera {camera_id} khong ton tai")
    realtime_service.publish(
        event_type="camera.deleted",
        resources=["cameras", "summary"],
        table="cameras",
        payload={"camera_id": camera_id},
    )


@router.post("/provision", response_model=CameraResponse)
async def sync_provision(data: ProvisionSync):
    return camera_service.sync_provisioning(data)


@router.post("/heartbeat", response_model=CameraResponse)
async def sync_heartbeat(data: CameraHeartbeat):
    try:
        return camera_service.sync_heartbeat(data)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/sync-devices")
async def sync_thingsboard_devices():
    try:
        return camera_service.sync_devices_from_thingsboard()
    except Exception as exc:
        raise HTTPException(500, f"Dong bo ThingsBoard that bai: {exc}")


@router.get("/{camera_id}/zones", response_model=List[ZoneResponse])
async def get_zones(camera_id: int):
    return camera_service.get_zones(camera_id)


@router.put("/{camera_id}/zones", response_model=List[ZoneResponse])
async def save_zones(camera_id: int, body: ZonesBulkUpdate):
    try:
        return camera_service.save_zones(camera_id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
