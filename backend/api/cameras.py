"""Camera REST API chuẩn cho dashboard, provisioning và live-view."""

from typing import List

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse

from models.camera import CameraCreate, CameraResponse, CameraUpdate, ProvisionSync
from models.zone import ZoneResponse, ZonesBulkUpdate
from services.camera_service import CameraService

router = APIRouter(prefix="/cameras", tags=["Cameras"])
_svc = CameraService()


@router.get("", response_model=List[CameraResponse])
async def list_cameras():
    return _svc.list_cameras()


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(data: CameraCreate):
    try:
        return _svc.register_camera(data)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: int):
    try:
        return _svc.get_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{camera_id}/live-view")
async def get_camera_live_view(camera_id: int):
    """Payload gọn cho overlay stream: thời gian, bbox, camera và trạng thái gần nhất."""
    try:
        return _svc.get_live_view(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{camera_id}/stream")
async def proxy_camera_stream(camera_id: int) -> StreamingResponse:
    """Proxy MJPEG stream để web hosting kết nối qua backend."""
    try:
        return await _svc.proxy_stream(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.get("/{camera_id}/snapshot")
async def proxy_camera_snapshot(camera_id: int) -> Response:
    """Proxy snapshot JPEG mới nhất từ camera."""
    try:
        return await _svc.proxy_snapshot(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, data: CameraUpdate):
    """Frontend cập nhật: tên, vị trí, stream URL, mô tả."""
    try:
        return _svc.update_camera(camera_id, data)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{camera_id}/factory-reset")
async def factory_reset_camera(camera_id: int):
    """Gửi lệnh xóa NVS và khởi động lại thiết bị qua ThingsBoard RPC."""
    try:
        return _svc.factory_reset_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Gửi lệnh factory reset thất bại: {exc}")


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int):
    from repositories.camera_repo import CameraRepository

    CameraRepository().delete(camera_id)


@router.post("/provision", response_model=CameraResponse)
async def sync_provision(data: ProvisionSync):
    """ESP32 gọi tự động sau khi có định danh để đồng bộ về backend."""
    return _svc.sync_provisioning(data)


@router.post("/sync-devices")
async def sync_thingsboard_devices():
    """Quét ThingsBoard và đồng bộ device mới về DB để web tự hiện camera."""
    try:
        return _svc.sync_devices_from_thingsboard()
    except Exception as exc:
        raise HTTPException(500, f"Đồng bộ ThingsBoard thất bại: {exc}")


@router.get("/{camera_id}/zones", response_model=List[ZoneResponse])
async def get_zones(camera_id: int):
    return _svc.get_zones(camera_id)


@router.put("/{camera_id}/zones", response_model=List[ZoneResponse])
async def save_zones(camera_id: int, body: ZonesBulkUpdate):
    """Thay toàn bộ zone của camera từ zone editor trên web."""
    try:
        return _svc.save_zones(camera_id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
