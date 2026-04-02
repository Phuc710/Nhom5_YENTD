"""Camera REST API cho dashboard admin."""

import json
import traceback
from typing import Any, List

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


def _device_identity(data: Any, mapped_camera_id: Any = None) -> str:
    cam = getattr(data, "camera_id", None)
    tb = getattr(data, "tb_device_name", None) or getattr(data, "device_name", None) or getattr(data, "tb_device_id", None)
    mac = getattr(data, "mac_address", None)
    ip = getattr(data, "ip_address", None)
    mapped = mapped_camera_id if mapped_camera_id not in (None, "") else "N/A"
    return f"cam_req={cam or 'N/A'} | cam_map={mapped} | tb={tb or 'N/A'} | mac={mac or 'N/A'} | ip={ip or 'N/A'}"


def _compact_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        return str(data)


@router.get("", response_model=List[CameraResponse])
async def list_cameras():
    cameras = camera_service.list_cameras()
    logger.info(
        "DANH SÁCH CAMERA | số lượng=%s | chi tiết=%s",
        len(cameras),
        [
            {
                "id": camera.get("camera_id"),
                "tên": camera.get("camera_name"),
                "online": camera.get("online"),
                "stream": camera.get("stream_running"),
                "máy_chủ": camera.get("stream_connected"),
            }
            for camera in cameras
        ],
    )
    return cameras


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


@router.get("/{camera_id}/live-view/sse")
async def get_camera_live_view_sse(camera_id: int):
    """Luồng Server-Sent Events (SSE) đẩy dữ liệu AI overlay real-time liên tục cho Web."""
    try:
        return StreamingResponse(
            camera_service.proxy_live_view_sse(camera_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
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


@router.delete("")
async def delete_all_cameras():
    from backend.services.stream_manager import stream_manager

    await stream_manager.stop_all()
    deleted = CameraRepository().delete_all()
    camera_service.invalidate_camera_cache()
    realtime_service.publish(
        event_type="camera.deleted_all",
        resources=["cameras", "summary"],
        table="cameras",
        payload={"deleted": deleted},
    )
    return {"ok": True, "deleted": deleted}


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int):
    deleted = CameraRepository().delete(camera_id)
    if not deleted:
        raise HTTPException(404, f"Camera {camera_id} không tồn tại")
    camera_service.invalidate_camera_cache()
    realtime_service.publish(
        event_type="camera.deleted",
        resources=["cameras", "summary"],
        table="cameras",
        payload={"camera_id": camera_id},
    )


@router.post("/provision", response_model=CameraResponse)
async def sync_provision(data: ProvisionSync):
    try:
        result = await camera_service.sync_provisioning(data)
        mapped_camera_id = result.get("camera_id") if isinstance(result, dict) else None
        logger.info(
            "✅ PROVISION OK | %s | response=%s",
            _device_identity(data, mapped_camera_id),
            _compact_json(
                {
                    "camera_id": result.get("camera_id"),
                    "camera_name": result.get("camera_name"),
                    "stream_url": result.get("stream_url"),
                    "online": result.get("online"),
                }
            ),
        )
        return result
    except ValueError as exc:
        logger.warning("❌ PROVISION REJECT | %s | err=%s", _device_identity(data), exc)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("❌ PROVISION FAIL | %s | err=%s\n%s", _device_identity(data), exc, traceback.format_exc())
        raise HTTPException(500, f"Lỗi đồng bộ provisioning: {exc}")


@router.post("/heartbeat")
async def sync_heartbeat(data: CameraHeartbeat):
    try:
        result = await camera_service.sync_heartbeat(data)
        mapped_camera_id = result.get("camera_id") if isinstance(result, dict) else None
        logger.info(
            "💓 HEARTBEAT OK | %s | light=%s | heap=%s | rssi=%s | response=%s",
            _device_identity(data, mapped_camera_id),
            getattr(data, "light_mode", None) or "N/A",
            getattr(data, "free_heap", None),
            getattr(data, "wifi_rssi", None),
            _compact_json(result),
        )
        return result
    except ValueError as exc:
        logger.warning("❌ HEARTBEAT REJECT | %s | err=%s", _device_identity(data), exc)
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error("❌ HEARTBEAT FAIL | %s | err=%s", _device_identity(data), exc)
        raise HTTPException(500, f"Lỗi heartbeat: {exc}")


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
