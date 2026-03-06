"""
services/camera_service.py — Business logic Camera + Provisioning + Zones
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from repositories.camera_repo import CameraRepository
from models.camera import CameraCreate, CameraUpdate, ProvisionSync
from models.zone import ZonesBulkUpdate


class CameraService:
    """Xử lý toàn bộ nghiệp vụ liên quan đến Camera"""

    def __init__(self):
        self._repo = CameraRepository()

    # ---- Camera CRUD ------------------------------------

    def list_cameras(self) -> List[Dict]:
        return self._repo.get_all()

    def get_camera(self, camera_id: int) -> Optional[Dict]:
        cam = self._repo.get_by_id(camera_id)
        if cam is None:
            raise ValueError(f"Camera {camera_id} không tồn tại")
        return cam

    def register_camera(self, data: CameraCreate) -> Dict:
        """Tạo camera mới (lần đầu provisioning hoặc thủ công)"""
        payload = data.model_dump(exclude_none=True)
        result = self._repo.create(payload)
        if result is None:
            raise RuntimeError("Tạo camera thất bại")
        return result

    def update_camera(self, camera_id: int, data: CameraUpdate) -> Dict:
        """Cập nhật thông tin camera từ frontend (tên, vị trí, stream URL...)"""
        if not self._repo.exists(camera_id):
            raise ValueError(f"Camera {camera_id} không tồn tại")
        payload = data.model_dump(exclude_none=True)
        if not payload:
            raise ValueError("Không có trường nào để cập nhật")
        result = self._repo.update(camera_id, payload)
        return result or {}

    # ---- Provisioning -----------------------------------

    def sync_provisioning(self, prov: ProvisionSync) -> Dict:
        """
        Được gọi khi ESP32 provision xong ThingsBoard.
        - Tạo camera trong DB nếu chưa có
        - Upsert thông tin provisioning (MAC, token, IP, fw)
        - Đặt status camera = active
        """
        if not self._repo.exists(prov.camera_id):
            self._repo.create({
                "camera_id": prov.camera_id,
                "camera_name": f"Camera {prov.camera_id}",
                "location": "Chưa cấu hình",
                "status": "active",
                "tb_device_name": prov.tb_device_id,
            })
        else:
            self._repo.update(prov.camera_id, {"status": "active"})

        prov_data = prov.model_dump(exclude_none=True)
        prov_data["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        prov_data["online"] = True
        self._repo.upsert_provisioning(prov_data)

        return self._repo.get_by_id(prov.camera_id) or {}

    def heartbeat(self, camera_id: int) -> None:
        """Cập nhật last_seen khi có telemetry/upload từ ESP32"""
        self._repo.touch_last_seen(camera_id)

    # ---- Detection Zones --------------------------------

    def get_zones(self, camera_id: int) -> List[Dict]:
        return self._repo.get_zones(camera_id)

    def save_zones(self, camera_id: int, body: ZonesBulkUpdate) -> List[Dict]:
        """Replace toàn bộ zones của camera"""
        if not self._repo.exists(camera_id):
            raise ValueError(f"Camera {camera_id} không tồn tại")
        zones = [z.model_dump() for z in body.zones]
        return self._repo.replace_zones(camera_id, zones)
