"""Nghiệp vụ camera, ThingsBoard, stream proxy và đồng bộ tự động."""

from datetime import datetime, timezone
import re
from typing import Any, AsyncIterator, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi.responses import Response, StreamingResponse

from backend.config.settings import get_settings
from backend.models.camera import CameraCreate, CameraHeartbeat, CameraUpdate, ProvisionSync
from backend.models.zone import ZonesBulkUpdate
from backend.repositories.camera_repository import CameraRepository
from backend.services.live_view_service import live_view_store
from backend.services.realtime_service import realtime_service
from backend.services.thingsboard_service import ThingsBoardService
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class CameraService:
    """Xử lý toàn bộ nghiệp vụ liên quan đến camera."""

    def __init__(self):
        self._camera_repository = CameraRepository()
        self._thingsboard_service = ThingsBoardService()
        self._settings = get_settings()

    def list_cameras(self) -> List[Dict]:
        cameras = self._camera_repository.get_all()
        provisionings = self._camera_repository.get_provisioning_many(
            [int(camera["camera_id"]) for camera in cameras if camera.get("camera_id") is not None]
        )
        return [
            self._hydrate_camera_record(camera, provisionings.get(int(camera["camera_id"])))
            for camera in cameras
        ]

    def get_camera(self, camera_id: int) -> Dict:
        camera = self._camera_repository.get_by_id(camera_id)
        if camera is None:
            raise ValueError(f"Camera {camera_id} không tồn tại")
        return self._hydrate_camera_record(camera)

    def get_live_view(self, camera_id: int) -> Dict[str, Any]:
        """Trả về dữ liệu stream overlay mới nhất cho web."""
        camera = self.get_camera(camera_id)
        overlay = live_view_store.get_state(camera_id)
        now = datetime.now(ZoneInfo(self._settings.timezone))

        return {
            "camera_id": camera["camera_id"],
            "camera_name": self._resolve_display_name(camera),
            "device_label": self._resolve_device_label(camera),
            "tb_device_name": camera.get("tb_device_name"),
            "device_name": camera.get("device_name"),
            "project_name": camera.get("project_name"),
            "device_model": camera.get("device_model"),
            "location": camera.get("location"),
            "stream_url": camera.get("stream_url"),
            "online": camera.get("online"),
            "timezone": self._settings.timezone,
            "server_time": now.isoformat(),
            "overlay": overlay,
        }

    async def register_camera(self, data: CameraCreate) -> Dict:
        """Tạo camera mới bằng provisioning hoặc khai báo thủ công."""
        payload = data.model_dump(exclude_none=True)
        payload.setdefault("camera_name", self._default_camera_name(data.camera_id))
        payload.setdefault("location", "Chưa cấu hình")
        result = self._camera_repository.create(payload)
        if result is None:
            raise RuntimeError("❌ Tạo camera thất bại")
        camera = self.get_camera(data.camera_id)
        self._publish_camera_event(
            event_type="camera.created",
            camera_id=data.camera_id,
            tb_device_name=camera.get("tb_device_name"),
        )
        return camera

    async def update_camera(self, camera_id: int, data: CameraUpdate) -> Dict:
        """Cập nhật thông tin camera từ dashboard."""
        if not self._camera_repository.exists(camera_id):
            raise ValueError(f"❌ Camera {camera_id} không tồn tại")
        payload = data.model_dump(exclude_none=True)
        if not payload:
            raise ValueError("⚠️ Không có trường nào để cập nhật")
        self._camera_repository.update(camera_id, payload)
        camera = self.get_camera(camera_id)
        self._publish_camera_event(
            event_type="camera.updated",
            camera_id=camera_id,
            tb_device_name=camera.get("tb_device_name"),
        )
        return camera

    async def sync_provisioning(self, prov: ProvisionSync) -> Dict:
        """Đồng bộ định danh thiết bị từ ESP32 và ThingsBoard về backend."""
        resolved_camera_id = self._resolve_provision_camera_id(prov)
        current = self._camera_repository.get_by_id(resolved_camera_id) or {}
        tb_name = prov.tb_device_name or prov.device_name or prov.tb_device_id
        requested_camera_id = self._coerce_int(prov.camera_id)
        if requested_camera_id and requested_camera_id != resolved_camera_id:
            logger.warning(
                "⚠️ Bỏ qua camera_id=%s vì định danh hiện tại map tới camera_id=%s (tb_device_name=%s, mac=%s)",
                requested_camera_id,
                resolved_camera_id,
                tb_name or "N/A",
                prov.mac_address or "N/A",
            )
        configured_name = prov.camera_name or current.get("configured_camera_name") or current.get("camera_name")
        device_identity_name = self._resolve_identity_name(
            camera_name=configured_name,
            tb_device_name=tb_name,
            device_name=prov.device_name,
            project_name=prov.project_name,
            camera_id=resolved_camera_id,
        )
        stream_url = self._resolve_stream_url(
            existing_stream_url=current.get("stream_url"),
            previous_stream_url=None,
            previous_ip=current.get("ip_address"),
            previous_host=current.get("stream_host"),
            previous_scheme=current.get("stream_scheme"),
            previous_port=current.get("stream_port"),
            previous_path=current.get("stream_path"),
            current_stream_url=prov.stream_url,
            current_ip=prov.ip_address,
            current_host=prov.stream_host,
            current_scheme=prov.stream_scheme,
            current_port=prov.stream_port,
            current_path=prov.stream_path,
        )
        desired_location = (
            (prov.location or "").strip()
            or current.get("location")
            or "Chưa cấu hình"
        )

        if not self._camera_repository.exists(resolved_camera_id):
            create_payload: Dict[str, Any] = {
                "camera_id": resolved_camera_id,
                "camera_name": device_identity_name,
                "location": desired_location,
                "status": "active",
            }
            if prov.latitude is not None:
                create_payload["latitude"] = prov.latitude
            if prov.longitude is not None:
                create_payload["longitude"] = prov.longitude
            if tb_name:
                create_payload["tb_device_name"] = tb_name
            if stream_url:
                create_payload["stream_url"] = stream_url
            self._camera_repository.create(create_payload)
        else:
            update_payload: Dict[str, Any] = {"status": "active"}
            if not current.get("camera_name") or self._is_placeholder_name(current.get("camera_name"), resolved_camera_id):
                update_payload["camera_name"] = device_identity_name
            if self._is_placeholder_location(current.get("location")) and prov.location:
                update_payload["location"] = desired_location
            if current.get("latitude") is None and prov.latitude is not None:
                update_payload["latitude"] = prov.latitude
            if current.get("longitude") is None and prov.longitude is not None:
                update_payload["longitude"] = prov.longitude
            if tb_name:
                update_payload["tb_device_name"] = tb_name
            if stream_url:
                update_payload["stream_url"] = stream_url
            self._camera_repository.update(resolved_camera_id, update_payload)

        raw_prov_data = prov.model_dump(exclude_none=True)
        raw_prov_data["camera_id"] = resolved_camera_id
        raw_prov_data["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        raw_prov_data["online"] = True
        provisioning_payload = self._sanitize_provisioning_payload(raw_prov_data)
        provisioning_payload["extra_attributes"] = self._build_extra_attributes(raw_prov_data)
        self._camera_repository.upsert_provisioning(provisioning_payload)

        logger.info(
            "📝 Đồng bộ provisioning | Cam: %s | MAC: %s | IP: %s | FW: %s",
            resolved_camera_id,
            prov.mac_address or "N/A",
            prov.ip_address or "N/A",
            prov.fw_version or "N/A",
        )
        camera = self.get_camera(resolved_camera_id)
        self._publish_camera_event(
            event_type="camera.provisioned",
            camera_id=resolved_camera_id,
            tb_device_name=camera.get("tb_device_name"),
        )
        return camera

    async def sync_heartbeat(self, heartbeat: CameraHeartbeat) -> Dict:
        """Cập nhật runtime cho camera đã được provisioning trước đó."""
        camera_id = self._resolve_heartbeat_camera_id(heartbeat)
        current = self._camera_repository.get_by_id(camera_id)
        if current is None:
            raise ValueError(f"❌ Camera {camera_id} không tồn tại")

        stream_url = self._resolve_stream_url(
            existing_stream_url=current.get("stream_url"),
            previous_stream_url=None,
            previous_ip=current.get("ip_address"),
            previous_host=current.get("stream_host"),
            previous_scheme=current.get("stream_scheme"),
            previous_port=current.get("stream_port"),
            previous_path=current.get("stream_path"),
            current_stream_url=heartbeat.stream_url,
            current_ip=heartbeat.ip_address,
            current_host=heartbeat.stream_host,
            current_scheme=heartbeat.stream_scheme,
            current_port=heartbeat.stream_port,
            current_path=heartbeat.stream_path,
        )

        update_payload: Dict[str, Any] = {"status": "active"}
        if heartbeat.tb_device_name:
            update_payload["tb_device_name"] = heartbeat.tb_device_name
        if stream_url:
            update_payload["stream_url"] = stream_url
        self._camera_repository.update(camera_id, update_payload)

        raw_data = heartbeat.model_dump(exclude_none=True)
        raw_data["camera_id"] = camera_id
        raw_data["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        raw_data["online"] = heartbeat.online if heartbeat.online is not None else True
        provisioning_payload = self._sanitize_provisioning_payload(raw_data)
        provisioning_payload["extra_attributes"] = self._build_extra_attributes(raw_data)
        self._camera_repository.upsert_provisioning(provisioning_payload)

        camera = self.get_camera(camera_id)
        self._publish_camera_event(
            event_type="camera.heartbeat",
            camera_id=camera_id,
            tb_device_name=camera.get("tb_device_name"),
        )
        return camera

    async def sync_devices_from_thingsboard(self) -> Dict[str, int]:
        """Đồng bộ danh sách device ThingsBoard về DB để web tự thấy camera mới."""
        devices = await self._thingsboard_service.list_devices()
        created = 0
        updated = 0
        scanned = 0

        for device in devices:
            if not self._should_sync_tb_device(device):
                continue

            scanned += 1
            result = self._upsert_device_from_thingsboard(device)
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1

        if scanned:
            logger.info(
                "🔄 Đồng bộ ThingsBoard hoàn tất | Quét: %s | Tạo mới: %s | Cập nhật: %s",
                scanned,
                created,
                updated,
            )
        if created or updated:
            realtime_service.publish(
                event_type="camera.sync",
                resources=["cameras", "summary"],
                table="cameras",
                payload={
                    "scanned": scanned,
                    "created": created,
                    "updated": updated,
                },
            )
        return {"scanned": scanned, "created": created, "updated": updated}

    def heartbeat(self, camera_id: int) -> None:
        """Cập nhật last_seen khi có heartbeat hoặc upload."""
        self._camera_repository.touch_last_seen(camera_id)
        self._publish_camera_event(event_type="camera.heartbeat", camera_id=camera_id)

    def get_zones(self, camera_id: int) -> List[Dict]:
        return self._camera_repository.get_zones(camera_id)

    def save_zones(self, camera_id: int, body: ZonesBulkUpdate) -> List[Dict]:
        """Thay thế toàn bộ vùng phát hiện của camera."""
        if not self._camera_repository.exists(camera_id):
            raise ValueError(f"Camera {camera_id} không tồn tại")
        zones = [zone.model_dump() for zone in body.zones]
        return self._camera_repository.replace_zones(camera_id, zones)

    async def factory_reset_camera(self, camera_id: int) -> Dict[str, Any]:
        """Gửi lệnh factory reset tới thiết bị qua ThingsBoard."""
        camera = self.get_camera(camera_id)
        tb_device_name = camera.get("tb_device_name")
        if not tb_device_name:
            prov = self._camera_repository.get_provisioning(camera_id) or {}
            tb_device_name = prov.get("tb_device_name") or prov.get("tb_device_id")

        result = await self._thingsboard_service.factory_reset_device(tb_device_name or "")
        logger.warning(
            "🧨 Đã yêu cầu factory reset | Cam: %s | TB: %s",
            camera_id,
            tb_device_name or "N/A",
        )
        return {"camera_id": camera_id, **result}

    async def reboot_camera(self, camera_id: int) -> Dict[str, Any]:
        """Gửi lệnh reboot tới camera."""
        camera = self.get_camera(camera_id)
        tb_name = camera.get("tb_device_name") or ""
        return {"camera_id": camera_id, **await self._thingsboard_service.reboot_device(tb_name)}

    async def start_ota_camera(self, camera_id: int, url: str) -> Dict[str, Any]:
        """Gửi lệnh cập nhật OTA."""
        camera = self.get_camera(camera_id)
        tb_name = camera.get("tb_device_name") or ""
        return {"camera_id": camera_id, **await self._thingsboard_service.start_ota_update(tb_name, url)}

    async def set_traffic_light_state(self, camera_id: int, state: str) -> Dict[str, Any]:
        """Gửi lệnh đổi trạng thái đèn (normal, red, green)."""
        camera = self.get_camera(camera_id)
        tb_name = camera.get("tb_device_name") or ""
        return {"camera_id": camera_id, **await self._thingsboard_service.set_traffic_light_mode(tb_name, state)}

    async def update_iot_config(self, camera_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """Cập nhật cấu hình Shared Attributes (vào ThingsBoard)."""
        camera = self.get_camera(camera_id)
        tb_name = camera.get("tb_device_name") or ""
        return {"camera_id": camera_id, **await self._thingsboard_service.update_shared_attributes(tb_name, config)}

    async def proxy_stream(self, camera_id: int) -> StreamingResponse:
        """Phát lại MJPEG stream từ camera qua backend để web hosting dễ nhúng."""
        camera = self.get_camera(camera_id)
        stream_url = camera.get("stream_url")
        if not stream_url:
            raise RuntimeError("Camera chưa có đường dẫn luồng phát (stream_url)")

        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=None),
            follow_redirects=True,
        )
        headers = {"Accept": "multipart/x-mixed-replace, image/jpeg;q=0.9, */*;q=0.8"}

        try:
            request = client.build_request("GET", stream_url, headers=headers)
            response = await client.send(request, stream=True)
            response.raise_for_status()
        except Exception as exc:
            await client.aclose()
            logger.error("Không mở được stream camera=%s url=%s: %s", camera_id, stream_url, exc)
            raise RuntimeError(f"Không kết nối được stream camera: {exc}") from exc

        media_type = response.headers.get("content-type", "multipart/x-mixed-replace; boundary=frame")

        async def stream_bytes() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        logger.info("Đã mở proxy stream camera=%s qua backend", camera_id)
        return StreamingResponse(
            stream_bytes(),
            media_type=media_type,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    async def proxy_snapshot(self, camera_id: int) -> Response:
        """Lấy snapshot JPEG mới nhất qua backend."""
        camera = self.get_camera(camera_id)
        stream_url = camera.get("stream_url")
        snapshot_path = self._normalize_stream_path(camera.get("stream_snapshot_path"), "/snapshot")
        if not stream_url:
            raise RuntimeError("Camera chưa có đường dẫn luồng phát (stream_url)")

        snapshot_url = stream_url.rstrip("/")
        if snapshot_url.endswith("/stream"):
            snapshot_url = f"{snapshot_url[:-7]}{snapshot_path}"
        else:
            snapshot_url = f"{snapshot_url}{snapshot_path}"

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(snapshot_url)
                resp.raise_for_status()
        except Exception as exc:
            logger.error("Không lấy được snapshot camera=%s url=%s: %s", camera_id, snapshot_url, exc)
            raise RuntimeError(f"Không lấy được snapshot camera: {exc}") from exc

        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @staticmethod
    def _default_camera_name(camera_id: int) -> str:
        return f"Camera {camera_id:03d}"

    def _resolve_display_name(self, camera: Dict[str, Any]) -> str:
        return (
            camera.get("camera_name")
            or camera.get("device_name")
            or camera.get("project_name")
            or camera.get("tb_device_name")
            or self._default_camera_name(int(camera["camera_id"]))
        )

    def _resolve_device_label(self, camera: Dict[str, Any]) -> str:
        return (
            camera.get("device_name")
            or camera.get("project_name")
            or camera.get("tb_device_name")
            or camera.get("camera_name")
            or self._default_camera_name(int(camera["camera_id"]))
        )

    def _resolve_identity_name(
        self,
        *,
        camera_name: Optional[str],
        tb_device_name: Optional[str],
        device_name: Optional[str],
        project_name: Optional[str],
        camera_id: int,
    ) -> str:
        if camera_name and not self._is_placeholder_name(camera_name, camera_id):
            return camera_name.strip()
        return (
            (device_name or "").strip()
            or (project_name or "").strip()
            or (tb_device_name or "").strip()
            or self._default_camera_name(camera_id)
        )

    def _is_placeholder_name(self, value: Optional[str], camera_id: int) -> bool:
        normalized = (value or "").strip().lower()
        placeholders = {
            f"camera {camera_id}".lower(),
            f"camera {camera_id:03d}".lower(),
            f"pcb cam ai s3 {camera_id}".lower(),
            f"pcb cam ai s3 {camera_id:03d}".lower(),
        }
        return normalized in placeholders

    def _is_placeholder_location(self, value: Optional[str]) -> bool:
        normalized = (value or "").strip().lower()
        return normalized in {"", "chua cau hinh", "chua co vi tri", "chưa cấu hình", "chưa có vị trí", "--"}

    def _should_sync_tb_device(self, device: Dict[str, Any]) -> bool:
        prefix = (self._settings.thingsboard_device_name_prefix or "").strip().lower()
        if not prefix:
            return True

        name = str(device.get("name") or "").strip().lower()
        label = str(device.get("label") or "").strip().lower()
        return prefix in name or prefix in label

    def _upsert_device_from_thingsboard(self, device: Dict[str, Any]) -> str:
        tb_device_name = str(device.get("name") or "").strip()
        if not tb_device_name:
            return "skipped"

        existing_camera = self._camera_repository.get_by_tb_device_name(tb_device_name)
        existing_provision = self._camera_repository.get_provisioning_by_tb_device_name(tb_device_name)
        runtime = device.get("runtime") or {}

        camera_id = self._resolve_camera_id(
            tb_device_name,
            existing_camera,
            existing_provision,
            runtime_camera_id=self._coerce_int(runtime.get("camera_id")),
        )
        current = existing_camera or (self._camera_repository.get_by_id(camera_id) or {})
        current_provision = existing_provision or self._camera_repository.get_provisioning(camera_id) or {}
        runtime_provision = self._merge_runtime_provisioning(current_provision, runtime)

        desired_name = self._resolve_identity_name(
            camera_name=current.get("camera_name"),
            tb_device_name=tb_device_name,
            device_name=runtime_provision.get("device_name"),
            project_name=runtime_provision.get("project_name"),
            camera_id=camera_id,
        )
        desired_location = (
            current.get("location")
            if not self._is_placeholder_location(current.get("location"))
            else runtime_provision.get("location")
        ) or current.get("location") or "Chưa cấu hình"
        desired_stream_url = self._resolve_stream_url(
            existing_stream_url=current.get("stream_url"),
            previous_stream_url=current_provision.get("stream_url"),
            previous_ip=current.get("ip_address") or current_provision.get("ip_address"),
            previous_host=current.get("stream_host") or current_provision.get("stream_host"),
            previous_scheme=current.get("stream_scheme") or current_provision.get("stream_scheme"),
            previous_port=current.get("stream_port") or current_provision.get("stream_port"),
            previous_path=current.get("stream_path") or current_provision.get("stream_path"),
            current_stream_url=runtime_provision.get("stream_url"),
            current_ip=runtime_provision.get("ip_address"),
            current_host=runtime_provision.get("stream_host"),
            current_scheme=runtime_provision.get("stream_scheme"),
            current_port=runtime_provision.get("stream_port"),
            current_path=runtime_provision.get("stream_path"),
        )

        camera_payload: Dict[str, Any] = {
            "camera_id": camera_id,
            "camera_name": desired_name,
            "location": desired_location,
            "tb_device_name": tb_device_name,
            "status": current.get("status") or ("active" if runtime_provision.get("online") else "inactive"),
        }
        if desired_stream_url:
            camera_payload["stream_url"] = desired_stream_url
        if current.get("description"):
            camera_payload["description"] = current["description"]
        if current.get("latitude") is not None:
            camera_payload["latitude"] = current["latitude"]
        if current.get("longitude") is not None:
            camera_payload["longitude"] = current["longitude"]

        if current:
            update_payload = {key: value for key, value in camera_payload.items() if key != "camera_id"}
            self._camera_repository.update(camera_id, update_payload)
            action = "updated"
        else:
            self._camera_repository.create(camera_payload)
            action = "created"

        provisioning_payload: Dict[str, Any] = {
            "camera_id": camera_id,
            "tb_device_id": (((device.get("id") or {}).get("id")) if isinstance(device.get("id"), dict) else device.get("id")),
            "tb_device_name": tb_device_name,
            "device_name": runtime_provision.get("device_name"),
            "project_name": runtime_provision.get("project_name"),
            "device_model": runtime_provision.get("device_model"),
            "wifi_ssid": runtime_provision.get("wifi_ssid"),
            "resolution": runtime_provision.get("resolution"),
            "fw_version": runtime_provision.get("fw_version"),
            "idf_version": runtime_provision.get("idf_version"),
            "mac_address": runtime_provision.get("mac_address"),
            "stream_scheme": runtime_provision.get("stream_scheme"),
            "stream_host": runtime_provision.get("stream_host"),
            "stream_port": runtime_provision.get("stream_port"),
            "stream_path": runtime_provision.get("stream_path"),
            "stream_snapshot_path": runtime_provision.get("stream_snapshot_path"),
            "ip_address": runtime_provision.get("ip_address"),
            "access_token": runtime_provision.get("access_token"),
            "last_seen_at": runtime_provision.get("last_seen_at"),
            "last_boot_at": runtime_provision.get("last_boot_at"),
            "online": runtime_provision.get("online", False),
        }
        provisioning_payload["extra_attributes"] = self._build_extra_attributes(runtime_provision)
        self._camera_repository.upsert_provisioning(provisioning_payload)
        return action

    def _resolve_camera_id(
        self,
        tb_device_name: str,
        existing_camera: Optional[Dict[str, Any]],
        existing_provision: Optional[Dict[str, Any]],
        runtime_camera_id: Optional[int] = None,
    ) -> int:
        if existing_camera and existing_camera.get("camera_id") is not None:
            return int(existing_camera["camera_id"])

        if existing_provision and existing_provision.get("camera_id") is not None:
            return int(existing_provision["camera_id"])

        if runtime_camera_id and runtime_camera_id > 0 and not self._camera_repository.exists(runtime_camera_id):
            return runtime_camera_id

        match = re.search(r"(\d{1,6})\s*$", tb_device_name)
        if match:
            candidate = int(match.group(1))
            if candidate > 0 and not self._camera_repository.exists(candidate):
                return candidate

        return self._camera_repository.get_next_camera_id()

    def _resolve_provision_camera_id(self, prov: ProvisionSync) -> int:
        tb_name = (prov.tb_device_name or prov.device_name or prov.tb_device_id or "").strip()
        tb_candidate: Optional[int] = None
        if tb_name:
            existing_camera = self._camera_repository.get_by_tb_device_name(tb_name)
            if existing_camera and existing_camera.get("camera_id") is not None:
                tb_candidate = int(existing_camera["camera_id"])
            else:
                existing_provision = self._camera_repository.get_provisioning_by_tb_device_name(tb_name)
                if existing_provision and existing_provision.get("camera_id") is not None:
                    tb_candidate = int(existing_provision["camera_id"])

        mac_candidate: Optional[int] = None
        if prov.mac_address:
            existing_by_mac = self._camera_repository.get_provisioning_by_mac(prov.mac_address)
            if existing_by_mac and existing_by_mac.get("camera_id") is not None:
                mac_candidate = int(existing_by_mac["camera_id"])

        candidates = {candidate for candidate in (tb_candidate, mac_candidate) if candidate is not None}
        if len(candidates) > 1:
            logger.warning(
                "Phát hiện mapping provisioning xung đột: tb_device_name=%s -> %s, mac=%s -> %s. Ưu tiên camera từ ThingsBoard.",
                tb_name or "chưa có",
                tb_candidate,
                prov.mac_address or "chưa có",
                mac_candidate,
            )

        if tb_candidate is not None:
            return tb_candidate
        if mac_candidate is not None:
            return mac_candidate

        requested_camera_id = self._coerce_int(prov.camera_id)
        if requested_camera_id and requested_camera_id > 0:
            return requested_camera_id

        return self._camera_repository.get_next_camera_id()

    def _resolve_heartbeat_camera_id(self, heartbeat: CameraHeartbeat) -> int:
        requested_camera_id = self._coerce_int(heartbeat.camera_id)
        if requested_camera_id and self._camera_repository.exists(requested_camera_id):
            return requested_camera_id

        tb_name = (heartbeat.tb_device_name or heartbeat.device_name or heartbeat.tb_device_id or "").strip()
        if tb_name:
            existing_camera = self._camera_repository.get_by_tb_device_name(tb_name)
            if existing_camera and existing_camera.get("camera_id") is not None:
                return int(existing_camera["camera_id"])

            existing_provision = self._camera_repository.get_provisioning_by_tb_device_name(tb_name)
            if existing_provision and existing_provision.get("camera_id") is not None:
                return int(existing_provision["camera_id"])

        if heartbeat.mac_address:
            existing_by_mac = self._camera_repository.get_provisioning_by_mac(heartbeat.mac_address)
            if existing_by_mac and existing_by_mac.get("camera_id") is not None:
                return int(existing_by_mac["camera_id"])

        raise ValueError("Khong tim thay camera da duoc provisioning cho heartbeat")

    @staticmethod
    def _normalize_stream_path(path: Optional[str], fallback: str) -> str:
        value = (path or "").strip() or fallback
        return value if value.startswith("/") else f"/{value}"

    def _build_stream_url(
        self,
        *,
        ip_address: Optional[str] = None,
        host: Optional[str] = None,
        scheme: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
    ) -> Optional[str]:
        stream_host = (host or ip_address or "").strip()
        if not stream_host:
            return None
        stream_scheme = (scheme or "http").strip().lower() or "http"
        stream_port = int(port or 81)
        stream_path = self._normalize_stream_path(path, "/stream")
        return f"{stream_scheme}://{stream_host}:{stream_port}{stream_path}"

    def _resolve_stream_url(
        self,
        existing_stream_url: Optional[str],
        previous_stream_url: Optional[str],
        previous_ip: Optional[str],
        previous_host: Optional[str],
        previous_scheme: Optional[str],
        previous_port: Optional[int],
        previous_path: Optional[str],
        current_stream_url: Optional[str],
        current_ip: Optional[str],
        current_host: Optional[str],
        current_scheme: Optional[str],
        current_port: Optional[int],
        current_path: Optional[str],
    ) -> Optional[str]:
        normalized_current_stream = (current_stream_url or "").strip() or None
        auto_stream_url = self._build_stream_url(
            ip_address=current_ip,
            host=current_host,
            scheme=current_scheme,
            port=current_port,
            path=current_path,
        )
        desired_stream_url = normalized_current_stream or auto_stream_url
        if not desired_stream_url:
            return existing_stream_url

        if not existing_stream_url:
            return desired_stream_url

        previous_auto_stream = self._build_stream_url(
            ip_address=previous_ip,
            host=previous_host,
            scheme=previous_scheme,
            port=previous_port,
            path=previous_path,
        )
        if previous_stream_url and existing_stream_url == previous_stream_url:
            return desired_stream_url
        if previous_auto_stream and existing_stream_url == previous_auto_stream:
            return desired_stream_url

        return existing_stream_url

    def _merge_runtime_provisioning(
        self,
        current_provision: Optional[Dict[str, Any]],
        runtime: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(current_provision or {})
        runtime = runtime or {}
        if not runtime:
            return merged

        for key in (
            "device_name",
            "project_name",
            "device_model",
            "wifi_ssid",
            "resolution",
            "fw_version",
            "mac_address",
            "reset_reason",
            "stream_url",
            "stream_scheme",
            "stream_host",
            "stream_path",
            "stream_snapshot_path",
            "ip_address",
            "location",
            "access_token",
            "last_boot_at",
            "tb_device_name",
            "target_fw_version",
            "ota_url",
            "device_state",
        ):
            value = runtime.get(key)
            if value not in (None, ""):
                merged[key] = value

        idf_version = self._first_non_empty(runtime.get("idf_version"), runtime.get("idf_ver"))
        if idf_version:
            merged["idf_version"] = idf_version

        for key in (
            "capture_interval_ms",
            "jpeg_quality",
            "telemetry_interval_ms",
            "tl_red_ms",
            "tl_yellow_ms",
            "tl_green_ms",
            "free_heap",
            "min_free_heap",
            "wifi_rssi",
            "uptime_s",
            "wifi_disconnect_count",
        ):
            value = self._coerce_int(runtime.get(key))
            if value is not None:
                merged[key] = value

        runtime_camera_id = self._coerce_int(runtime.get("camera_id"))
        if runtime_camera_id:
            merged["camera_id"] = runtime_camera_id

        stream_port = self._coerce_int(runtime.get("stream_port"))
        if stream_port:
            merged["stream_port"] = stream_port

        cpu_temp = self._coerce_float(runtime.get("cpu_temp"))
        if cpu_temp is not None:
            merged["cpu_temp"] = cpu_temp

        light_mode = self._normalize_light_mode(runtime.get("Light_Mode"))
        if light_mode:
            merged["light_mode"] = light_mode

        online = self._coerce_online_flag(runtime)
        if online is not None:
            merged["online"] = online
            if online:
                merged["last_seen_at"] = datetime.now(timezone.utc).isoformat()

        return merged

    def _hydrate_camera_record(
        self,
        camera: Dict[str, Any],
        provisioning: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        camera_data = dict(camera or {})
        if not camera_data:
            return camera_data

        camera_id = self._coerce_int(camera_data.get("camera_id"))
        provisioning = provisioning or (self._camera_repository.get_provisioning(camera_id) if camera_id else None) or {}
        extra_attributes = provisioning.get("extra_attributes") or {}
        if not isinstance(extra_attributes, dict):
            extra_attributes = {}

        for key in (
            "device_name",
            "project_name",
            "device_model",
            "wifi_ssid",
            "resolution",
            "stream_scheme",
            "stream_host",
            "stream_port",
            "stream_path",
            "stream_snapshot_path",
            "ip_address",
            "fw_version",
            "idf_version",
            "mac_address",
            "reset_reason",
            "last_seen_at",
            "last_boot_at",
            "online",
        ):
            if camera_data.get(key) in (None, "") and provisioning.get(key) not in (None, ""):
                camera_data[key] = provisioning.get(key)

        for key in (
            "capture_interval_ms",
            "jpeg_quality",
            "telemetry_interval_ms",
            "tl_red_ms",
            "tl_yellow_ms",
            "tl_green_ms",
            "target_fw_version",
            "ota_url",
            "cpu_temp",
            "free_heap",
            "min_free_heap",
            "wifi_rssi",
            "uptime_s",
            "device_state",
            "light_mode",
            "wifi_disconnect_count",
        ):
            if camera_data.get(key) in (None, "") and extra_attributes.get(key) not in (None, ""):
                camera_data[key] = extra_attributes.get(key)

        if not camera_data.get("location") and provisioning.get("location"):
            camera_data["location"] = provisioning["location"]

        camera_data["extra_attributes"] = extra_attributes
        return camera_data

    def _build_extra_attributes(self, source: Dict[str, Any]) -> Dict[str, Any]:
        extra: Dict[str, Any] = {}
        if not source:
            return extra

        for key in (
            "reset_reason",
            "location",
            "stream_url",
            "target_fw_version",
            "ota_url",
            "device_state",
        ):
            value = source.get(key)
            if value not in (None, ""):
                extra[key] = value

        for key in (
            "capture_interval_ms",
            "jpeg_quality",
            "telemetry_interval_ms",
            "tl_red_ms",
            "tl_yellow_ms",
            "tl_green_ms",
            "free_heap",
            "min_free_heap",
            "wifi_rssi",
            "uptime_s",
            "wifi_disconnect_count",
        ):
            value = self._coerce_int(source.get(key))
            if value is not None:
                extra[key] = value

        cpu_temp = self._coerce_float(source.get("cpu_temp"))
        if cpu_temp is not None:
            extra["cpu_temp"] = cpu_temp

        light_mode = self._normalize_light_mode(source.get("light_mode") or source.get("Light_Mode"))
        if light_mode:
            extra["light_mode"] = light_mode

        return extra

    @staticmethod
    def _sanitize_provisioning_payload(source: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = {
            "camera_id",
            "tb_device_id",
            "tb_device_name",
            "device_name",
            "project_name",
            "device_model",
            "wifi_ssid",
            "resolution",
            "access_token",
            "mac_address",
            "fw_version",
            "idf_version",
            "stream_scheme",
            "stream_host",
            "stream_port",
            "stream_path",
            "stream_snapshot_path",
            "ip_address",
            "last_seen_at",
            "last_boot_at",
            "online",
            "extra_attributes",
        }
        return {
            key: value
            for key, value in source.items()
            if key in allowed_keys and value is not None
        }

    @staticmethod
    def _first_non_empty(*values: Any) -> Optional[str]:
        for value in values:
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                return normalized
        return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_light_mode(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        normalized = str(value).strip().upper()
        if normalized in {"RED", "YELLOW", "GREEN"}:
            return normalized
        return None

    @staticmethod
    def _coerce_online_flag(runtime: Dict[str, Any]) -> Optional[bool]:
        raw_status = (
            runtime.get("device_status")
            or runtime.get("status")
            or runtime.get("device_state")
        )
        if raw_status in (None, ""):
            return None
        normalized = str(raw_status).strip().lower()
        if normalized in {"online", "active", "healthy", "running", "ota", "true", "1", "yes"}:
            return True
        if normalized in {"offline", "inactive", "error", "down", "false", "0", "no"}:
            return False
        return None

    @staticmethod
    def _publish_camera_event(
        *,
        event_type: str,
        camera_id: int,
        tb_device_name: Optional[str] = None,
    ) -> None:
        realtime_service.publish(
            event_type=event_type,
            resources=["cameras", "summary"],
            table="cameras",
            payload={
                "camera_id": camera_id,
                "tb_device_name": tb_device_name,
            },
        )
