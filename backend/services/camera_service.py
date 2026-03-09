"""Nghiệp vụ camera, provisioning và vùng phát hiện."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.camera import CameraCreate, CameraUpdate, ProvisionSync
from models.zone import ZonesBulkUpdate
from repositories.camera_repo import CameraRepository
from services.thingsboard_service import ThingsBoardService
from utils.logger import get_logger

logger = get_logger(__name__)


class CameraService:
    """Xử lý toàn bộ nghiệp vụ liên quan đến camera."""

    def __init__(self):
        self._repo = CameraRepository()
        self._tb = ThingsBoardService()

    def list_cameras(self) -> List[Dict]:
        return self._repo.get_all()

    def get_camera(self, camera_id: int) -> Optional[Dict]:
        cam = self._repo.get_by_id(camera_id)
        if cam is None:
            raise ValueError(f"Camera {camera_id} không tồn tại")
        return cam

    def register_camera(self, data: CameraCreate) -> Dict:
        """Tạo camera mới bằng provisioning hoặc khai báo thủ công."""
        payload = data.model_dump(exclude_none=True)
        result = self._repo.create(payload)
        if result is None:
            raise RuntimeError("Tạo camera thất bại")
        return result

    def update_camera(self, camera_id: int, data: CameraUpdate) -> Dict:
        """Cập nhật thông tin camera từ dashboard."""
        if not self._repo.exists(camera_id):
            raise ValueError(f"Camera {camera_id} không tồn tại")
        payload = data.model_dump(exclude_none=True)
        if not payload:
            raise ValueError("Không có trường nào để cập nhật")
        result = self._repo.update(camera_id, payload)
        return result or {}

    def sync_provisioning(self, prov: ProvisionSync) -> Dict:
        """Đồng bộ định danh thiết bị từ ESP32/ThingsBoard về backend."""
        current = self._repo.get_by_id(prov.camera_id) or {}
        tb_name = prov.tb_device_name or prov.tb_device_id
        stream_url = self._resolve_stream_url(
            existing_stream_url=current.get("stream_url"),
            previous_ip=current.get("ip_address"),
            current_ip=prov.ip_address,
        )

        if not self._repo.exists(prov.camera_id):
            create_payload: Dict[str, Any] = {
                "camera_id": prov.camera_id,
                "camera_name": f"Camera {prov.camera_id}",
                "location": "Chưa cấu hình",
                "status": "active",
            }
            if tb_name:
                create_payload["tb_device_name"] = tb_name
            if stream_url:
                create_payload["stream_url"] = stream_url
            self._repo.create(create_payload)
        else:
            update_payload: Dict[str, Any] = {"status": "active"}
            if tb_name:
                update_payload["tb_device_name"] = tb_name
            if stream_url:
                update_payload["stream_url"] = stream_url
            self._repo.update(prov.camera_id, update_payload)

        prov_data = prov.model_dump(exclude_none=True)
        prov_data["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        prov_data["online"] = True
        self._repo.upsert_provisioning(prov_data)

        logger.info(
            "Đồng bộ provisioning camera=%s mac=%s ip=%s fw=%s",
            prov.camera_id,
            prov.mac_address or "chưa có",
            prov.ip_address or "chưa có",
            prov.fw_version or "chưa có",
        )
        return self._repo.get_by_id(prov.camera_id) or {}

    def heartbeat(self, camera_id: int) -> None:
        """Cập nhật last_seen khi có heartbeat hoặc upload."""
        self._repo.touch_last_seen(camera_id)

    def get_zones(self, camera_id: int) -> List[Dict]:
        return self._repo.get_zones(camera_id)

    def save_zones(self, camera_id: int, body: ZonesBulkUpdate) -> List[Dict]:
        """Thay thế toàn bộ vùng phát hiện của camera."""
        if not self._repo.exists(camera_id):
            raise ValueError(f"Camera {camera_id} không tồn tại")
        zones = [z.model_dump() for z in body.zones]
        return self._repo.replace_zones(camera_id, zones)

    def factory_reset_camera(self, camera_id: int) -> Dict[str, Any]:
        """Gửi lệnh factory reset tới thiết bị qua ThingsBoard."""
        camera = self.get_camera(camera_id)
        tb_device_name = camera.get("tb_device_name")
        if not tb_device_name:
            prov = self._repo.get_provisioning(camera_id) or {}
            tb_device_name = prov.get("tb_device_name") or prov.get("tb_device_id")

        result = self._tb.factory_reset_device(tb_device_name or "")
        logger.warning(
            "Đã yêu cầu factory reset camera=%s tb_device_name=%s",
            camera_id,
            tb_device_name or "chưa có",
        )
        return {
            "camera_id": camera_id,
            **result,
        }

    @staticmethod
    def _build_stream_url(ip_address: Optional[str]) -> Optional[str]:
        if not ip_address:
            return None
        return f"http://{ip_address}/stream"

    def _resolve_stream_url(
        self,
        existing_stream_url: Optional[str],
        previous_ip: Optional[str],
        current_ip: Optional[str],
    ) -> Optional[str]:
        auto_stream_url = self._build_stream_url(current_ip)
        if not auto_stream_url:
            return None

        if not existing_stream_url:
            return auto_stream_url

        previous_auto_stream = self._build_stream_url(previous_ip)
        if previous_auto_stream and existing_stream_url == previous_auto_stream:
            return auto_stream_url

        return existing_stream_url
