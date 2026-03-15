"""Camera REST API cho dashboard admin."""

import traceback
from typing import List

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse

from backend.models.camera import (
    CameraCreate,
    CameraHeartbeat,
    CameraResponse,
    CameraUpdate,
    OtaRequest,
    ProvisionSync,
    TrafficLightRequest,
)
from backend.models.zone import ZoneResponse, ZonesBulkUpdate
from backend.repositories.camera_repository import CameraRepository
from backend.services.realtime_service import realtime_service
from backend.services.camera_service import CameraService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/cameras", tags=["Cameras"])
camera_service = CameraService()


@router.get("", response_model=List[CameraResponse])
async def list_cameras():
    return camera_service.list_cameras()


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(data: CameraCreate):
    try:
        return await camera_service.register_camera(data)
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



@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, data: CameraUpdate):
    try:
        return await camera_service.update_camera(camera_id, data)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{camera_id}/factory-reset")
async def factory_reset_camera(camera_id: int):
    try:
        return await camera_service.factory_reset_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Gửi lệnh khôi phục cài đặt gốc thất bại: {exc}")


@router.post("/{camera_id}/reboot")
async def reboot_camera(camera_id: int):
    try:
        return await camera_service.reboot_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.post("/{camera_id}/ota")
async def start_camera_ota(camera_id: int, data: OtaRequest):
    try:
        return await camera_service.start_ota_camera(camera_id, data.url)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.post("/{camera_id}/traffic-light")
async def set_camera_traffic_light(camera_id: int, data: TrafficLightRequest):
    try:
        return await camera_service.set_traffic_light_state(camera_id, data.state)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.put("/{camera_id}/iot-config")
async def update_camera_iot_config(camera_id: int, data: dict):
    """Cập nhật cấu hình IoT vào ThingsBoard."""
    try:
        return await camera_service.update_iot_config(camera_id, data)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int):
    deleted = CameraRepository().delete(camera_id)
    if not deleted:
        raise HTTPException(404, f"Camera {camera_id} không tồn tại")
    realtime_service.publish(
        event_type="camera.deleted",
        resources=["cameras", "summary"],
        table="cameras",
        payload={"camera_id": camera_id},
    )


@router.post("/provision", response_model=CameraResponse)
async def sync_provision(data: ProvisionSync):
    try:
        return await camera_service.sync_provisioning(data)
    except ValueError as exc:
        logger.warning("Provision bị từ chối (400): %s", exc)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("Provision thất bại (500): %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, f"Lỗi đồng bộ provisioning: {exc}")


@router.post("/heartbeat", response_model=CameraResponse)
async def sync_heartbeat(data: CameraHeartbeat):
    try:
        return await camera_service.sync_heartbeat(data)
    except ValueError as exc:
        logger.warning("Heartbeat bị từ chối camera không tồn tại: %s", exc)
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error("Heartbeat thất bại (500): %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, f"Lỗi đồng bộ heartbeat: {exc}")


@router.post("/sync-devices")
async def sync_thingsboard_devices():
    try:
        return await camera_service.sync_devices_from_thingsboard()
    except Exception as exc:
        raise HTTPException(500, f"Đồng bộ ThingsBoard thất bại: {exc}")


@router.get("/{camera_id}/zones", response_model=List[ZoneResponse])
async def get_zones(camera_id: int):
    return camera_service.get_zones(camera_id)


@router.put("/{camera_id}/zones", response_model=List[ZoneResponse])
async def save_zones(camera_id: int, body: ZonesBulkUpdate):
    """Lưu zones và reload vào stream worker ngay lập tức."""
    try:
        result = camera_service.save_zones(camera_id, body)
        # Reload zones vào stream worker đang chạy
        from backend.services.stream_manager import stream_manager
        await stream_manager.reload_zones(camera_id)
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc))
