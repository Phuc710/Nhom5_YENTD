"""
api/cameras.py — Camera REST API
  GET    /api/cameras               — Danh sách
  POST   /api/cameras               — Tạo camera mới
  GET    /api/cameras/{id}          — Chi tiết
  PUT    /api/cameras/{id}          — Cập nhật (từ frontend)
  DELETE /api/cameras/{id}          — Xóa
  POST   /api/cameras/provision     — Sync provisioning ESP32 → DB
  GET    /api/cameras/{id}/zones    — Lấy zones
  PUT    /api/cameras/{id}/zones    — Lưu zones
"""
from fastapi import APIRouter, HTTPException, status
from typing import List

from models.camera import CameraCreate, CameraUpdate, CameraResponse, ProvisionSync, ProvisionResponse
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
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: int):
    try:
        return _svc.get_camera(camera_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, data: CameraUpdate):
    """Frontend cập nhật: tên, vị trí, stream URL, mô tả"""
    try:
        return _svc.update_camera(camera_id, data)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{camera_id}/factory-reset")
async def factory_reset_camera(camera_id: int):
    """Dashboard web chỉ có 1 nút reset: xóa toàn bộ NVS rồi reboot."""
    try:
        return _svc.factory_reset_camera(camera_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(500, f"Gửi lệnh factory reset thất bại: {e}")


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int):
    from repositories.camera_repo import CameraRepository
    CameraRepository().delete(camera_id)


# ---- Provisioning ----------------------------------------

@router.post("/provision", response_model=CameraResponse)
async def sync_provision(data: ProvisionSync):
    """Gọi tự động khi ESP32 provision xong — tạo/update DB"""
    return _svc.sync_provisioning(data)


# ---- Detection Zones -------------------------------------

@router.get("/{camera_id}/zones", response_model=List[ZoneResponse])
async def get_zones(camera_id: int):
    return _svc.get_zones(camera_id)


@router.put("/{camera_id}/zones", response_model=List[ZoneResponse])
async def save_zones(camera_id: int, body: ZonesBulkUpdate):
    """Replace toàn bộ zones của camera (từ Zone Editor)"""
    try:
        return _svc.save_zones(camera_id, body)
    except ValueError as e:
        raise HTTPException(404, str(e))
