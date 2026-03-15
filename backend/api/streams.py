"""API quản lý stream workers per camera."""
from fastapi import APIRouter, HTTPException
from typing import Optional

from backend.services.stream_manager import stream_manager
from backend.services.camera_service import CameraService
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/streams")
_camera_service = CameraService()


@router.get("")
async def list_stream_status():
    """Trạng thái tất cả stream workers."""
    return stream_manager.status()


@router.get("/{camera_id}")
async def get_stream_status(camera_id: int):
    """Trạng thái stream worker của 1 camera."""
    return stream_manager.status(camera_id)


@router.post("/{camera_id}/start")
async def start_stream(camera_id: int):
    """Khởi động stream worker cho camera."""
    try:
        camera = _camera_service.get_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))

    stream_url = camera.get("stream_url")
    if not stream_url:
        raise HTTPException(400, f"Camera {camera_id} chưa có stream_url")

    ok = await stream_manager.start_camera(camera_id, stream_url)
    if not ok:
        raise HTTPException(500, f"Không thể khởi động stream cam={camera_id}")

    logger.info("▶️  Start stream | Cam: %s | URL: %s", camera_id, stream_url)
    return {"ok": True, "camera_id": camera_id, "stream_url": stream_url}


@router.post("/{camera_id}/stop")
async def stop_stream(camera_id: int):
    """Dừng stream worker cho camera."""
    ok = await stream_manager.stop_camera(camera_id)
    logger.info("⏹️  Stop stream | Cam: %s", camera_id)
    return {"ok": ok, "camera_id": camera_id}


@router.post("/{camera_id}/reload-zones")
async def reload_zones(camera_id: int):
    """Tải lại zones cho stream worker (gọi sau khi lưu zones từ web UI)."""
    ok = await stream_manager.reload_zones(camera_id)
    if not ok:
        raise HTTPException(404, f"Không có stream worker đang chạy cho cam={camera_id}")
    return {"ok": True, "camera_id": camera_id, "message": "Zones đã được tải lại"}
