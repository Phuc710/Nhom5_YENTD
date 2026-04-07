import asyncio
import json
import os
from datetime import datetime, timezone
import re
import time
from threading import Lock
from typing import Any, AsyncIterator, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

from backend.config.settings import get_settings
from backend.models.camera import CameraCreate, CameraHeartbeat, CameraUpdate, ProvisionSync
from backend.models.zone import ZonesBulkUpdate
from backend.repositories.camera_repository import CameraRepository
from backend.services.thingsboard_service import ThingsBoardService
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class CameraService:
    """Xử lý toàn bộ nghiệp vụ liên quan đến camera."""

    def __init__(self):
        self._camera_repository = CameraRepository()
        self._thingsboard_service = ThingsBoardService()
        self._settings = get_settings()
        self._stream_sync_tasks: Dict[int, asyncio.Task] = {}
        self._camera_list_cache: List[Dict[str, Any]] = []
        self._last_known_camera_list: List[Dict[str, Any]] = []
        self._camera_list_cache_until = 0.0
        self._last_known_camera_list_at = 0.0
        self._camera_list_cache_ttl_seconds = 2.0
        self._camera_list_grace_seconds = 20.0
        self._camera_list_grace_seconds = 20.0
        self._camera_list_cache_lock = Lock()
        
        # In-memory MAC → camera_id cache: tránh gọi Supabase mỗi heartbeat
        self._mac_to_camera_id: Dict[str, int] = {}
        self._tb_to_camera_id: Dict[str, int] = {}
        self._identity_cache_lock = Lock()
        self._identity_cache_file_lock = Lock()
        
        # Thư mục lưu cache JSON
        self._data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(self._data_dir, exist_ok=True)
        self._identity_cache_file = os.path.join(self._data_dir, "identity_cache.json")
        
        self._pending_heartbeat_tasks: Dict[int, asyncio.Task] = {}
        self._last_stream_sync_at: Dict[int, float] = {}

    def list_cameras(self) -> List[Dict]:
        cached = self._get_cached_camera_list()
        if cached is not None:
            return cached

        cameras = self._build_camera_list()
        if not cameras:
            fallback = self._get_last_known_camera_list()
            if fallback is not None:
                logger.info(
                    "CAMERAS | Giữ danh sách camera gần nhất vì runtime stream vẫn đang hoạt động"
                )
                self._set_cached_camera_list(fallback)
                return [dict(camera) for camera in fallback]

        self._set_cached_camera_list(cameras)
        if cameras:
            self._set_last_known_camera_list(cameras)
        return [dict(camera) for camera in cameras]

    def _build_camera_list(self) -> List[Dict]:
        cameras = self._camera_repository.get_all()
        provisionings = self._camera_repository.get_provisioning_many(
            [int(camera["camera_id"]) for camera in cameras if camera.get("camera_id") is not None]
        )
        stream_status_map = self._get_stream_status_map()
        hydrated = [
            self._attach_stream_status(
                self._hydrate_camera_record(camera, provisionings.get(int(camera["camera_id"]))),
                stream_status_map.get(int(camera["camera_id"])),
            )
            for camera in cameras
        ]
        return [
            camera
            for camera in hydrated
            if camera.get("camera_id") is not None and self._is_visible_camera(camera)
        ]

    def get_camera(self, camera_id: int) -> Dict:
        camera = self._camera_repository.get_by_id(camera_id)
        if camera is None:
            raise ValueError(f"Camera {camera_id} không tồn tại")
        hydrated = self._attach_stream_status(
            self._hydrate_camera_record(camera),
            self._get_stream_status(camera_id),
        )
        if not self._is_visible_camera(hydrated):
            raise ValueError(f"Camera {camera_id} không tồn tại")
        return hydrated

    def invalidate_camera_cache(self) -> None:
        self._invalidate_camera_list_cache()

    async def register_camera(self, data: CameraCreate) -> Dict:
        """Tạo camera mới bằng provisioning hoặc khai báo thủ công."""
        payload = data.model_dump(exclude_none=True)
        payload.setdefault("camera_name", self._default_camera_name(data.camera_id))
        payload.setdefault("location", "Chưa cấu hình")
        result = self._camera_repository.create(payload)
        if result is None:
            raise RuntimeError("❌ Tạo camera thất bại")
        self._invalidate_camera_list_cache()
        camera = self.get_camera(data.camera_id)
        self._publish_camera_event(
            event_type="camera.created",
            camera_id=data.camera_id,
            tb_device_name=camera.get("tb_device_name"),
        )
        return camera

    def _load_identity_cache_from_disk(self) -> bool:
        """Đọc cache từ JSON file. Trả về True nếu thành công."""
        try:
            if not os.path.exists(self._identity_cache_file):
                return False
            with open(self._identity_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            with self._identity_cache_lock:
                self._mac_to_camera_id = data.get("mac_to_camera_id", {})
                self._tb_to_camera_id = data.get("tb_to_camera_id", {})
            logger.info("🖼️  [CORE] ✅ Load identity cache từ disk: %s MACs, %s TB names", len(self._mac_to_camera_id), len(self._tb_to_camera_id))
            return True
        except Exception as exc:
            logger.warning("⚠️ Lỗi load identity cache từ disk: %s", exc)
            return False

    def _save_identity_cache_to_disk(self) -> None:
        """Lưu cache hiện tại xuống JSON file."""
        try:
            with self._identity_cache_lock:
                data = {
                    "mac_to_camera_id": self._mac_to_camera_id,
                    "tb_to_camera_id": self._tb_to_camera_id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            with self._identity_cache_file_lock:
                # Ghi ra file tạm rồi rename để tránh corrupt nếu đang ghi bị mất điện
                tmp_file = self._identity_cache_file + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_file, self._identity_cache_file)
        except Exception as exc:
            logger.warning("⚠️ Lỗi lưu identity cache xuống disk: %s", exc)

    def _schedule_save_identity_cache(self) -> None:
        """Lên lịch lưu cache xuống disk trên một luồng nền nhẹ."""
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, self._save_identity_cache_to_disk)

    def warm_identity_cache(self, force_db: bool = False) -> None:
        """Nạp định danh: ưu tiên load JSON disk, nếu không có thì query DB rồi save JSON."""
        # Bước 1: Thử load từ disk nếu không bị ép load DB
        if not force_db and self._load_identity_cache_from_disk():
            return
            
        # Bước 2: Không có trên disk (hoặc force_db) -> Query từ Database
        try:
            if force_db:
                logger.info("🔄 Reload identity cache từ Database...")
            else:
                logger.info("🔄 Không tìm thấy JSON identity cache. Khởi tạo từ Database...")
            mappings = self._camera_repository.get_all_provisioning_lookups()
            count = 0
            with self._identity_cache_lock:
                self._mac_to_camera_id.clear()
                self._tb_to_camera_id.clear()
                for m in mappings:
                    cid = m.get("camera_id")
                    if cid is None: continue
                    mac = (m.get("mac_address") or "").upper().strip()
                    tb = (m.get("tb_device_name") or "").strip()
                    if mac: self._mac_to_camera_id[mac] = int(cid)
                    if tb:  self._tb_to_camera_id[tb] = int(cid)
                    count += 1
            
            logger.info("🖼️  [CORE] ✅ Nạp DB cache xong %s camera mappings. Đã lưu về JSON disk.", count)
            # Lưu ngay sau khi kéo từ DB
            self._save_identity_cache_to_disk()
            
        except Exception as exc:
            logger.warning("⚠️ Identity cache: nạp từ DB thất bại (sẽ fallback load lazily): %s", exc)

    async def update_camera(self, camera_id: int, data: CameraUpdate) -> Dict:
        """Cập nhật thông tin camera từ dashboard."""
        self._camera_repository.update(camera_id, data.model_dump(exclude_none=True))
        self._invalidate_camera_list_cache()
        self._publish_camera_event(event_type="camera.updated", camera_id=camera_id)
        return self.get_camera(camera_id)

    def _resolve_camera_id_fast(self, data: Any) -> Optional[int]:
        """Resolve camera_id từ in-memory cache — O(1), không gọi DB.
        Chấp nhận cả CameraHeartbeat và ProvisionSync.
        """
        mac = getattr(data, "mac_address", None)
        mac = (mac or "").upper().strip()
        
        # Thử lấy các định danh ThingsBoard
        tb_device_name = getattr(data, "tb_device_name", None)
        device_name = getattr(data, "device_name", None)
        tb_device_id = getattr(data, "tb_device_id", None)
        tb = (tb_device_name or device_name or tb_device_id or "").strip()
        
        with self._identity_cache_lock:
            if mac and mac in self._mac_to_camera_id:
                return self._mac_to_camera_id[mac]
            if tb and tb in self._tb_to_camera_id:
                return self._tb_to_camera_id[tb]
        return None

    async def sync_provisioning(self, prov: ProvisionSync) -> Dict:
        """Đồng bộ định danh thiết bị — phản hồi ngay, xử lý nền.

        [B1] Resolve/Assign camera_id (O(1) hoặc 1 DB call nếu cực kỳ mới)
        [B2] Return fast_camera snapshot ngay ~10ms
        [B3] Background: Toàn bộ logic DB (update cam, update prov, publish event)
        """
        # ── B1: Resolve identity ─────────────────────────────────────────────────
        camera_id = self._resolve_camera_id_fast(prov)
        if camera_id is None:
            camera_id = self._resolve_provision_camera_id(prov)
            
        mac = (prov.mac_address or "").upper().strip()
        tb  = (prov.tb_device_name or prov.device_name or "").strip()
        needs_save = False
        
        with self._identity_cache_lock:
            if mac and self._mac_to_camera_id.get(mac) != camera_id:
                self._mac_to_camera_id[mac] = camera_id
                needs_save = True
            if tb and self._tb_to_camera_id.get(tb) != camera_id:
                self._tb_to_camera_id[tb] = camera_id
                needs_save = True
                
        if needs_save:
            self._schedule_save_identity_cache()

        # ── B2: Trả về ngay ──────────────────────────────────────────────────────
        self._invalidate_camera_list_cache()

        # Resolve stream_url ngay từ ESP32 payload (không chờ background task)
        stream_url = prov.stream_url or (f"http://{prov.ip_address}:81/stream" if prov.ip_address else None)

        logger.info("⚡ [PROVISION] ✅ mac=%s | cam=%s | ip=%s | stream=%s",
                     prov.mac_address, camera_id, prov.ip_address, stream_url)

        # Trả về snapshot nhanh
        current = self._get_camera_from_list_cache(camera_id) or {}
        fast_camera = {
            **current,
            "camera_id": camera_id,
            "stream_url": stream_url,
            "online": True,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }

        # ── B3: Background task xử lý tất cả I/O ──────────────────────────────────
        self._schedule_provisioning_db_write_full(camera_id, prov)

        return fast_camera

    def _schedule_provisioning_db_write_full(
        self,
        camera_id: int,
        prov: ProvisionSync,
    ) -> None:
        """Thực hiện toàn bộ logic DB provisioning ở nền."""
        async def _run() -> None:
            try:
                loop = asyncio.get_running_loop()

                # Phase 1: resolve metadata & exists check
                exists = await loop.run_in_executor(None, lambda: self._camera_repository.exists(camera_id))
                current = self._get_camera_from_list_cache(camera_id) or {}

                # ── LOG RÕ RÀNG: CREATE vs RECONNECT ─────────────────────────
                _mac  = prov.mac_address or "N/A"
                _name = prov.device_name or prov.tb_device_name or prov.camera_name or f"cam-{camera_id}"
                _ip   = prov.ip_address or "N/A"
                if not exists:
                    logger.info("📷 [CREATE   ] cam=%-3s | %-20s | mac=%s | ip=%s", camera_id, _name, _mac, _ip)
                else:
                    logger.info("🔄 [RECONNECT] cam=%-3s | %-20s | mac=%s | ip=%s", camera_id, _name, _mac, _ip)
                # ─────────────────────────────────────────────────────────────

                tb_name = prov.tb_device_name or prov.device_name or prov.tb_device_id
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
                identity_name = self._resolve_identity_name(
                    camera_name=prov.camera_name or current.get("configured_camera_name") or current.get("camera_name"),
                    tb_device_name=tb_name,
                    device_name=prov.device_name,
                    project_name=prov.project_name,
                    camera_id=camera_id,
                )
                location = (prov.location or "").strip() or current.get("location") or "Vị trí chưa xác định"

                cam_payload = {
                    "camera_name": identity_name,
                    "location": location,
                    "tb_device_name": tb_name,
                    "stream_url": stream_url,
                    "status": "active",
                }
                if prov.latitude is not None: cam_payload["latitude"] = prov.latitude
                if prov.longitude is not None: cam_payload["longitude"] = prov.longitude

                raw = prov.model_dump(exclude_none=True)
                raw.update({"camera_id": camera_id, "last_seen_at": datetime.now(timezone.utc).isoformat(), "online": True})
                prov_payload = self._sanitize_provisioning_payload(raw)
                prov_payload["extra_attributes"] = self._build_extra_attributes(raw)

                # Phase 2: DB writes — camera FIRST if new (FK constraint), then provisioning
                if not exists:
                    # Sequential: cameras row must exist before camera_provisioning FK can be satisfied
                    await loop.run_in_executor(None, lambda: self._camera_repository.create({**cam_payload, "camera_id": camera_id}))
                    await loop.run_in_executor(None, lambda: self._camera_repository.upsert_provisioning(prov_payload))
                else:
                    # Parallel: both rows already exist, safe to run concurrently
                    tasks = [
                        loop.run_in_executor(None, lambda: self._camera_repository.update(camera_id, cam_payload)),
                        loop.run_in_executor(None, lambda: self._camera_repository.upsert_provisioning(prov_payload)),
                    ]
                    await asyncio.gather(*tasks)

                if prov.mac_address:
                    await loop.run_in_executor(None, lambda: self._camera_repository.clear_provisioning_mac_except(prov.mac_address, camera_id))
                # Phase 3: Event (stream worker đã start ở fast path)
                self._publish_camera_event(event_type="camera.provisioned", camera_id=camera_id, tb_device_name=tb_name)
            except Exception as exc:
                logger.error("❌ [prov bg] cam=%s lỗi: %s", camera_id, exc, exc_info=True)
                return

        asyncio.create_task(_run(), name=f"full_prov_{camera_id}")

    async def sync_heartbeat(self, heartbeat: CameraHeartbeat) -> Dict:
        """Nhịp sống từ ESP32 — phản hồi ngay, xử lý nền.

        [B1] Resolve camera_id: in-memory cache O(1)
        [B2] Update live_view_store: in-memory, 0 I/O
        [B3] Return {"ok": true} ngay ~5ms
        [B4] Background: stream sync + DB writes
        """
        # ── B1: Resolve camera_id ─────────────────────────────────────────────────
        camera_id = self._resolve_camera_id_fast(heartbeat)
        if camera_id is None:
            camera_id = self._resolve_heartbeat_camera_id(heartbeat)
            
        mac = (heartbeat.mac_address or "").upper().strip()
        tb  = (heartbeat.tb_device_name or heartbeat.device_name or "").strip()
        needs_save = False
        
        with self._identity_cache_lock:
            if mac and self._mac_to_camera_id.get(mac) != camera_id:
                self._mac_to_camera_id[mac] = camera_id
                needs_save = True
            if tb and self._tb_to_camera_id.get(tb) != camera_id:
                self._tb_to_camera_id[tb]  = camera_id
                needs_save = True
                
        if needs_save:
            self._schedule_save_identity_cache()

        # ── B2: Update state (in-memory) ──────────────────────────────────────────
        # Nhận cả light_state (mới) lẫn light_mode (cũ) — backward compatible
        effective_light = heartbeat.light_state or heartbeat.light_mode
        self._invalidate_camera_list_cache()

        # ── B3: Return ngầy ───────────────────────────────────────────────────────
        # ── B4: Background — stream sync + DB writes ──────────────────────────────
        self._schedule_heartbeat_background(camera_id, heartbeat)

        return {
            "ok": True,
            "camera_id": camera_id,
            "tb_device_name": heartbeat.tb_device_name or heartbeat.device_name or heartbeat.tb_device_id,
            "mac_address": heartbeat.mac_address,
            "ip_address": heartbeat.ip_address,
            "light_state": effective_light,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }


    def _schedule_heartbeat_background(
        self,
        camera_id: int,
        heartbeat: CameraHeartbeat,
    ) -> None:
        """Stream sync + DB writes chạy nền, không block heartbeat."""
        # Cleanup các task đã xong để giải phóng RAM
        done_keys = [k for k, t in self._pending_heartbeat_tasks.items() if t.done()]
        for k in done_keys:
            self._pending_heartbeat_tasks.pop(k, None)

        existing = self._pending_heartbeat_tasks.get(camera_id)
        if existing and not existing.done():
            existing.cancel()

        async def _run() -> None:
            loop = asyncio.get_running_loop()
            current = self._get_camera_from_list_cache(camera_id)

            # Resolve stream URL (CPU only)
            stream_url = self._resolve_stream_url(
                existing_stream_url=(current or {}).get("stream_url"),
                previous_stream_url=None,
                previous_ip=(current or {}).get("ip_address"),
                previous_host=(current or {}).get("stream_host"),
                previous_scheme=(current or {}).get("stream_scheme"),
                previous_port=(current or {}).get("stream_port"),
                previous_path=(current or {}).get("stream_path"),
                current_stream_url=heartbeat.stream_url,
                current_ip=heartbeat.ip_address,
                current_host=heartbeat.stream_host,
                current_scheme=heartbeat.stream_scheme,
                current_port=heartbeat.stream_port,
                current_path=heartbeat.stream_path,
            )
            fast_camera = self._build_fast_camera_snapshot(camera_id, heartbeat, stream_url, current)
            # Chỉ sync stream worker nếu cần thiết (IP/URL thay đổi hoặc worker chưa chạy)
            # Debounce: Tránh gọi dập dìu khi có nhiều heartbeat ảo
            self._schedule_stream_worker_sync(fast_camera, reason="heartbeat")

            # DB writes (parallel)
            now_iso = datetime.now(timezone.utc).isoformat()
            cam_update: Dict[str, Any] = {"status": "active"}
            if heartbeat.tb_device_name: cam_update["tb_device_name"] = heartbeat.tb_device_name
            if stream_url:               cam_update["stream_url"] = stream_url

            raw = heartbeat.model_dump(exclude_none=True)
            raw.update({"camera_id": camera_id, "last_seen_at": now_iso,
                        "online": heartbeat.online if heartbeat.online is not None else True})
            prov_payload = self._sanitize_provisioning_payload(raw)
            prov_payload["extra_attributes"] = self._build_extra_attributes(raw)

            try:
                await asyncio.gather(
                    loop.run_in_executor(None, lambda: self._camera_repository.update(camera_id, cam_update)),
                    loop.run_in_executor(None, lambda: self._camera_repository.upsert_provisioning(prov_payload)),
                )
            except Exception as exc:
                logger.warning("⚠️ [heartbeat bg] DB write lỗi cam=%s: %s", camera_id, exc)

            # Publish event nếu cần
            previous_online = self._compute_effective_online(current or {})
            if self._should_publish_runtime_change(
                current=current or {}, next_camera=fast_camera, previous_online=previous_online
            ):
                self._publish_camera_event(
                    event_type="camera.heartbeat",
                    camera_id=camera_id,
                    tb_device_name=fast_camera.get("tb_device_name"),
                )

        task = asyncio.create_task(_run(), name=f"hb_bg_{camera_id}")
        self._pending_heartbeat_tasks[camera_id] = task

    def _get_camera_from_list_cache(self, camera_id: int) -> Optional[Dict[str, Any]]:
        """Lấy camera từ list cache mà không gọi DB."""
        with self._camera_list_cache_lock:
            for cam in self._camera_list_cache:
                if cam.get("camera_id") == camera_id:
                    return dict(cam)
        return None

    def _build_fast_camera_snapshot(
        self,
        camera_id: int,
        heartbeat: CameraHeartbeat,
        stream_url: Optional[str],
        current: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Tạo camera dict nhanh từ heartbeat data + cached data."""
        base = dict(current) if current else {}
        effective_light = heartbeat.light_state or heartbeat.light_mode
        base.update({
            "camera_id": camera_id,
            "status": "active",
            "online": heartbeat.online if heartbeat.online is not None else True,
            "ip_address": heartbeat.ip_address or base.get("ip_address"),
            "stream_url": stream_url or base.get("stream_url"),
            "tb_device_name": heartbeat.tb_device_name or base.get("tb_device_name"),
            "light_state": effective_light or base.get("light_state") or base.get("light_mode"),
            "light_mode":  effective_light or base.get("light_mode"),  # backward compat
            "free_heap": heartbeat.free_heap,
            "wifi_rssi": heartbeat.wifi_rssi,
            "uptime_s": heartbeat.uptime_s,
            "cpu_temp": heartbeat.cpu_temp,
            "fw_version": heartbeat.fw_version or base.get("fw_version"),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        })

        # Attach stream worker status
        stream_status = self._get_stream_status(camera_id)
        return self._attach_stream_status(base, stream_status)

    def _schedule_heartbeat_db_write(
        self,
        camera_id: int,
        heartbeat: CameraHeartbeat,
        stream_url: Optional[str],
        camera: Dict[str, Any],
        previous_online: bool,
    ) -> None:
        """Đẩy việc ghi DB vào asyncio background task — không block heartbeat response."""
        # Hủy task cũ nếu còn đang chờ (debounce)
        existing = self._pending_heartbeat_tasks.get(camera_id)
        if existing and not existing.done():
            existing.cancel()

        async def _write_to_db() -> None:
            try:
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

                if self._should_publish_runtime_change(
                    current=camera,
                    next_camera=camera,
                    previous_online=previous_online,
                ):
                    self._publish_camera_event(
                        event_type="camera.runtime_changed",
                        camera_id=camera_id,
                        tb_device_name=camera.get("tb_device_name"),
                    )
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("❌ Heartbeat DB write thất bại cam=%s: %s", camera_id, exc)
            finally:
                self._pending_heartbeat_tasks.pop(camera_id, None)

        try:
            task = asyncio.create_task(_write_to_db(), name=f"heartbeat_db_{camera_id}")
            self._pending_heartbeat_tasks[camera_id] = task
        except RuntimeError:
            # Không có event loop (unit test, v.v.)
            pass

    async def sync_devices_from_thingsboard(self) -> Dict[str, int]:
        """Đồng bộ danh sách device ThingsBoard về DB để web tự thấy camera mới."""
        devices = await self._thingsboard_service.list_devices()
        created = 0
        updated = 0
        scanned = 0
        seen_identities: set[str] = set()

        for device in devices:
            if not self._should_sync_tb_device(device):
                continue
            identity_key = self._get_thingsboard_identity_key(device)
            if identity_key and identity_key in seen_identities:
                logger.info(
                    "Bỏ qua device ThingsBoard cũ trùng định danh | key=%s | name=%s",
                    identity_key,
                    str(device.get("name") or "").strip() or "N/A",
                )
                continue
            if identity_key:
                seen_identities.add(identity_key)

            scanned += 1
            result = self._upsert_device_from_thingsboard(device)
            action = result.get("action")
            camera_id = result.get("camera_id")
            if action == "created" and camera_id is not None:
                self._schedule_stream_worker_sync(
                    self.get_camera(int(camera_id)),
                    reason="thingsboard_sync",
                )

            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1

        if scanned:
            logger.info(
                "🤝 [THINGSBOARD] Đồng bộ hoàn tất | Quét: %d | Tạo mới: %d | Cập nhật: %d",
                scanned,
                created,
                updated,
            )
        if created or updated:
            self._invalidate_camera_list_cache()
            logger.info(
                "🤝 [THINGSBOARD] Camera sync | scanned=%d created=%d updated=%d",
                scanned, created, updated
            )
        return {"scanned": scanned, "created": created, "updated": updated}

    async def close(self) -> None:
        tasks = list(self._stream_sync_tasks.values())
        self._stream_sync_tasks.clear()
        hb_tasks = list(self._pending_heartbeat_tasks.values())
        self._pending_heartbeat_tasks.clear()
        all_tasks = tasks + hb_tasks
        if all_tasks:
            for task in all_tasks:
                task.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)
        await self._thingsboard_service.close()

    # Deleted duplicate warm_identity_cache that was overwriting JSON cache method

    def _extract_realtime_record(self, payload: Dict[str, Any]) -> tuple[str, str, Dict[str, Any]]:
        data = payload.get("data") or {}
        table = str(data.get("table") or payload.get("table") or "")
        event = str(data.get("type") or payload.get("eventType") or payload.get("type") or "").upper()
        record = data.get("record") or {}
        if not record:
            record = data.get("old_record") or {}
        return table, event, record

    def _apply_identity_mapping_from_record(self, table: str, record: Dict[str, Any]) -> bool:
        camera_id = self._coerce_int(record.get("camera_id"))
        if camera_id is None:
            return False

        mac = ""
        tb_name = ""
        if table == "camera_provisioning":
            mac = str(record.get("mac_address") or "").upper().strip()
            tb_name = str(
                record.get("tb_device_name")
                or record.get("device_name")
                or record.get("tb_device_id")
                or ""
            ).strip()
        elif table == "cameras":
            tb_name = str(record.get("tb_device_name") or record.get("camera_name") or "").strip()

        changed = False
        with self._identity_cache_lock:
            if mac and self._mac_to_camera_id.get(mac) != camera_id:
                self._mac_to_camera_id[mac] = camera_id
                changed = True
            if tb_name and self._tb_to_camera_id.get(tb_name) != camera_id:
                self._tb_to_camera_id[tb_name] = camera_id
                changed = True
        return changed

    def on_camera_db_changed(self, payload: Dict[str, Any]) -> None:
        """Callback được gọi khi Supabase Realtime báo DB thay đổi.

        Xóa cache để lần load tiếp theo lấy dữ liậu mới nhất từ Supabase,
        và kích hoạt reload stream worker nếu cần.
        """
        self._invalidate_camera_list_cache()
        table, event, record = self._extract_realtime_record(payload)

        # UPDATE/INSERT có record đầy đủ thì cập nhật map trực tiếp, không reload DB.
        if event != "DELETE" and record:
            if self._apply_identity_mapping_from_record(table, record):
                self._schedule_save_identity_cache()
            return

        # DELETE hoặc payload thiếu dữ liệu mới fallback reload từ DB.
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._enqueue_identity_reload)
        except RuntimeError:
            self.warm_identity_cache(force_db=True)

    def _enqueue_identity_reload(self) -> None:
        """Thực thi nạp lại identity cache trên event loop."""
        def _reload():
            self.warm_identity_cache(force_db=True)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _reload)

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

    async def proxy_stream(self, camera_id: int, request=None):
        """Không còn dùng trong Qt app — stream trực tiếp từ ESP32."""
        raise RuntimeError("proxy_stream không còn hoạt động trong Qt app")

    async def proxy_snapshot(self, camera_id: int):
        """Snapshot fallback trực tiếp từ ESP32."""
        camera = self.get_camera(camera_id)
        stream_url = camera.get("stream_url") or ""
        if not stream_url:
            raise RuntimeError("Camera chưa có stream_url")
        snapshot_url = stream_url.rstrip("/").replace("/stream", "/snapshot")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(snapshot_url)
            if resp.status_code == 200:
                return resp.content
        raise RuntimeError(f"Không lấy được snapshot từ {snapshot_url}")

    @staticmethod
    def _default_camera_name(camera_id: int) -> str:
        return f"Camera {camera_id:03d}"

    def _resolve_display_name(self, camera: Dict[str, Any]) -> str:
        return (
            camera.get("camera_name")
            or camera.get("device_name")
            or camera.get("mac_address")
            or camera.get("project_name")
            or camera.get("tb_device_name")
            or self._default_camera_name(int(camera["camera_id"]))
        )

    def _resolve_device_label(self, camera: Dict[str, Any]) -> str:
        return (
            camera.get("mac_address")
            or camera.get("device_name")
            or camera.get("project_name")
            or camera.get("tb_device_name")
            or camera.get("camera_name")
            or self._default_camera_name(int(camera["camera_id"]))
        )

    def _is_visible_camera(self, camera: Dict[str, Any]) -> bool:
        if not camera:
            return False

        def normalized(value: Optional[Any]) -> str:
            return str(value or "").strip().lower()

        identity_fields = (
            normalized(camera.get("camera_name")),
            normalized(camera.get("tb_device_name")),
            normalized(camera.get("device_name")),
            normalized(camera.get("project_name")),
            normalized(camera.get("location")),
        )
        stream_url = normalized(camera.get("stream_url"))

        has_real_identity = any(not self._is_placeholder_scalar(value) for value in identity_fields)
        has_valid_stream = (
            self._is_placeholder_scalar(stream_url)
            or stream_url.startswith("http://")
            or stream_url.startswith("https://")
        )

        if not has_valid_stream:
            return False

        if not has_real_identity and not camera.get("last_seen_at") and not camera.get("online"):
            return False

        return True

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
        if self._is_placeholder_scalar(normalized):
            return True
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
        name = str(device.get("name") or "").strip().lower()
        label = str(device.get("label") or "").strip().lower()

        if self._is_placeholder_scalar(name) and self._is_placeholder_scalar(label):
            return False

        if not prefix:
            return True

        return prefix in name or prefix in label

    def _get_thingsboard_identity_key(self, device: Dict[str, Any]) -> Optional[str]:
        runtime = device.get("runtime") or {}
        mac_addr = str(runtime.get("mac_address") or "").strip().upper()
        if not self._is_placeholder_scalar(mac_addr):
            return f"mac:{mac_addr}"

        tb_device_name = str(device.get("name") or "").strip().lower()
        if not self._is_placeholder_scalar(tb_device_name):
            return f"name:{tb_device_name}"
        return None

    def _upsert_device_from_thingsboard(self, device: Dict[str, Any]) -> Dict[str, Any]:
        tb_device_name = str(device.get("name") or "").strip()
        if not tb_device_name:
            return {"action": "skipped", "camera_id": None}

        runtime = device.get("runtime") or {}
        mac_addr = runtime.get("mac_address")
        if not self._has_reliable_device_identity(tb_device_name, runtime):
            logger.info(
                "Bỏ qua device ThingsBoard thiếu định danh ổn định | name=%s | mac=%s | stream=%s",
                tb_device_name or "N/A",
                mac_addr or "N/A",
                runtime.get("stream_url") or "N/A",
            )
            return {"action": "skipped", "camera_id": None}
        
        # Prioritize MAC address lookup for identity persistence
        existing_camera = None
        existing_provision = None
        
        if mac_addr:
            existing_provision = self._camera_repository.get_provisioning_by_mac(mac_addr)
            if existing_provision:
                existing_camera = self._camera_repository.get_by_id(existing_provision["camera_id"])
        
        if not existing_camera:
            existing_camera = self._camera_repository.get_by_tb_device_name(tb_device_name)
        if not existing_provision:
            existing_provision = self._camera_repository.get_provisioning_by_tb_device_name(tb_device_name)

        camera_id = self._resolve_camera_id(
            tb_device_name,
            existing_camera,
            existing_provision,
        )
        current = existing_camera or (self._camera_repository.get_by_id(camera_id) or {})
        current_provision = existing_provision or self._camera_repository.get_provisioning(camera_id) or {}
        runtime_provision = self._merge_runtime_provisioning(current_provision, runtime)
        prefer_runtime_register = self._is_recent_timestamp(
            current_provision.get("last_seen_at") or current.get("last_seen_at")
        )

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
        if prefer_runtime_register:
            desired_stream_url = (
                current.get("stream_url")
                or current_provision.get("stream_url")
                or runtime_provision.get("stream_url")
            )
        else:
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
            "status": current.get("status") or ("active" if prefer_runtime_register or runtime_provision.get("online") else "inactive"),
        }
        if desired_stream_url:
            camera_payload["stream_url"] = desired_stream_url
        if current.get("description"):
            camera_payload["description"] = current["description"]
        if current.get("latitude") is not None:
            camera_payload["latitude"] = current["latitude"]
        if current.get("longitude") is not None:
            camera_payload["longitude"] = current["longitude"]

        camera_changed = False
        if current:
            update_payload = {key: value for key, value in camera_payload.items() if key != "camera_id"}
            camera_changed = self._payload_has_changes(current, update_payload)
            if camera_changed:
                self._camera_repository.update(camera_id, update_payload)
            action = "updated" if camera_changed else "unchanged"
        else:
            self._camera_repository.create(camera_payload)
            action = "created"

        network_runtime = current_provision if prefer_runtime_register else runtime_provision
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
            "stream_scheme": network_runtime.get("stream_scheme"),
            "stream_host": network_runtime.get("stream_host"),
            "stream_port": network_runtime.get("stream_port"),
            "stream_path": network_runtime.get("stream_path"),
            "stream_snapshot_path": network_runtime.get("stream_snapshot_path"),
            "ip_address": network_runtime.get("ip_address"),
            "access_token": runtime_provision.get("access_token"),
            "last_seen_at": network_runtime.get("last_seen_at"),
            "last_boot_at": network_runtime.get("last_boot_at"),
            "online": network_runtime.get("online", False),
        }
        provisioning_payload["extra_attributes"] = self._build_extra_attributes(runtime_provision)
        provisioning_changed = self._payload_has_changes(current_provision, provisioning_payload)
        if action == "created" or provisioning_changed:
            self._camera_repository.upsert_provisioning(provisioning_payload)

        if action == "unchanged" and provisioning_changed:
            action = "updated"

        return {"action": action, "camera_id": camera_id, "tb_device_name": tb_device_name}

    def _resolve_camera_id(
        self,
        tb_device_name: str,
        existing_camera: Optional[Dict[str, Any]],
        existing_provision: Optional[Dict[str, Any]],
    ) -> int:
        if existing_camera and existing_camera.get("camera_id") is not None:
            return int(existing_camera["camera_id"])

        if existing_provision and existing_provision.get("camera_id") is not None:
            return int(existing_provision["camera_id"])

        match = re.search(r"(\d{1,6})\s*$", tb_device_name)
        if match:
            candidate = int(match.group(1))
            if candidate > 0 and not self._camera_repository.exists(candidate):
                return candidate

        return self._camera_repository.get_next_camera_id()

    def _resolve_provision_camera_id(self, prov: ProvisionSync) -> int:
        tb_name = (prov.tb_device_name or prov.device_name or prov.tb_device_id or "").strip()
        tb_candidate = self._find_camera_id_by_tb_name(tb_name)
        mac_candidate = self._find_camera_id_by_mac(prov.mac_address)

        # Ưu tiên MAC để giữ identity ổn định qua các lần reconnect/re-provision.
        # Nếu tin vào camera_id do device gửi lên, device có thể "nhảy id" và tạo camera mới không mong muốn.
        if mac_candidate is not None and mac_candidate > 0:
            if tb_candidate is not None and tb_candidate != mac_candidate:
                logger.warning(
                    "Identity conflict on provision, keep MAC mapping | mac=%s -> camera=%s | tb=%s -> camera=%s",
                    prov.mac_address or "N/A",
                    mac_candidate,
                    tb_name or "N/A",
                    tb_candidate,
                )
            return mac_candidate

        if tb_candidate is not None:
            return tb_candidate

        return self._camera_repository.get_next_camera_id()

    def _resolve_heartbeat_camera_id(self, heartbeat: CameraHeartbeat) -> int:
        tb_name = (heartbeat.tb_device_name or heartbeat.device_name or heartbeat.tb_device_id or "").strip()
        mac_candidate = self._find_camera_id_by_mac(heartbeat.mac_address)
        tb_candidate = self._find_camera_id_by_tb_name(tb_name)

        if mac_candidate is not None:
            if tb_candidate is not None and tb_candidate != mac_candidate:
                logger.warning(
                    "Xung đột định danh khi định danh (provision), ưu tiên MAC | mac=%s -> camera=%s | tb=%s -> camera=%s",
                    heartbeat.mac_address or "N/A",
                    mac_candidate,
                    tb_name or "N/A",
                    tb_candidate,
                )
            return mac_candidate

        if tb_candidate is not None:
            return tb_candidate

        raise ValueError("Khong tim thay camera da duoc provisioning cho heartbeat")

    def _find_camera_id_by_mac(self, mac_address: Optional[str]) -> Optional[int]:
        if not mac_address:
            return None
        existing_by_mac = self._camera_repository.get_provisioning_by_mac(mac_address)
        if existing_by_mac and existing_by_mac.get("camera_id") is not None:
            return int(existing_by_mac["camera_id"])
        return None

    def _find_camera_id_by_tb_name(self, tb_name: Optional[str]) -> Optional[int]:
        if not tb_name:
            return None

        existing_camera = self._camera_repository.get_by_tb_device_name(tb_name)
        if existing_camera and existing_camera.get("camera_id") is not None:
            return int(existing_camera["camera_id"])

        existing_provision = self._camera_repository.get_provisioning_by_tb_device_name(tb_name)
        if existing_provision and existing_provision.get("camera_id") is not None:
            return int(existing_provision["camera_id"])

        return None

    def _should_publish_runtime_change(
        self,
        *,
        current: Dict[str, Any],
        next_camera: Dict[str, Any],
        previous_online: bool,
    ) -> bool:
        if not previous_online:
            return True

        current_stream = str(current.get("stream_url") or "").strip()
        next_stream = str(next_camera.get("stream_url") or "").strip()
        if current_stream != next_stream:
            return True

        current_tb = str(current.get("tb_device_name") or "").strip()
        next_tb = str(next_camera.get("tb_device_name") or "").strip()
        if current_tb != next_tb:
            return True

        current_status = str(current.get("status") or "").strip().lower()
        next_status = str(next_camera.get("status") or "").strip().lower()
        return current_status != next_status

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

        # Runtime metadata from ESP should refresh the effective stream URL.
        if normalized_current_stream or current_ip or current_host:
            return desired_stream_url

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

    @staticmethod
    async def _sync_stream_worker(camera: Optional[Dict[str, Any]]) -> None:
        # Không còn dùng backend stream workers
        return

    def _schedule_stream_worker_sync(self, camera: Optional[Dict[str, Any]], reason: str) -> None:
        if not camera:
            return
        if not self._settings.enable_stream_workers:
            return

        camera_id = int(camera["camera_id"])
        # Debounce: Chỉ sync nếu chưa sync trong 15s gần nhất hoặc do provision
        now = time.monotonic()
        last_sync = self._last_stream_sync_at.get(camera_id, 0)
        if reason != "provision" and (now - last_sync) < 15.0:
            return
        self._last_stream_sync_at[camera_id] = now

        camera_id = self._coerce_int(camera.get("camera_id"))
        if camera_id is None:
            return

        existing_task = self._stream_sync_tasks.get(camera_id)
        if existing_task and not existing_task.done():
            return

        async def runner() -> None:
            try:
                logger.info(
                    "Đang tự đồng bộ stream worker | Cam: %s | reason=%s",
                    camera_id,
                    reason,
                )
                await self._sync_stream_worker(camera)
            except Exception as exc:
                logger.warning(
                    "Không thể tự đồng bộ stream worker | Cam: %s | reason=%s | %s",
                    camera_id,
                    reason,
                    exc,
                )
            finally:
                current_task = asyncio.current_task()
                if self._stream_sync_tasks.get(camera_id) is current_task:
                    self._stream_sync_tasks.pop(camera_id, None)

        self._stream_sync_tasks[camera_id] = asyncio.create_task(
            runner(),
            name=f"camera_stream_sync_{camera_id}",
        )

    def _payload_has_changes(self, current: Optional[Dict[str, Any]], payload: Dict[str, Any]) -> bool:
        current = current or {}
        for key, value in payload.items():
            if not self._change_values_equal(current.get(key), value):
                return True
        return False

    @staticmethod
    def _change_values_equal(left: Any, right: Any) -> bool:
        if isinstance(left, dict) or isinstance(right, dict):
            return (left or {}) == (right or {})

        if left in (None, "") and right in (None, ""):
            return True

        if isinstance(left, bool) or isinstance(right, bool):
            return bool(left) == bool(right)

        try:
            if left is not None and right is not None and str(left).strip() != "" and str(right).strip() != "":
                if float(left) == float(right):
                    return True
        except (TypeError, ValueError):
            pass

        return str(left or "").strip() == str(right or "").strip()

    @staticmethod
    def _get_stream_status(camera_id: int) -> Dict[str, Any]:
        return {}

    def _get_stream_status_map(self) -> Dict[int, Dict[str, Any]]:
        return {}

    def _attach_stream_status(
        self,
        camera: Dict[str, Any],
        stream_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        camera_data = dict(camera or {})
        if not camera_data:
            return camera_data

        status = stream_status
        camera_id = self._coerce_int(camera_data.get("camera_id"))
        if status is None and camera_id is not None:
            status = self._get_stream_status(camera_id)
        status = status or {}

        camera_data["stream_running"] = bool(status.get("running"))
        camera_data["stream_connected"] = bool(status.get("connected"))
        camera_data["stream_retry_count"] = self._coerce_int(status.get("retry_count")) or 0
        camera_data["stream_last_error"] = status.get("last_error")
        camera_data["stream_last_connected_at"] = status.get("last_connected_at")
        camera_data["stream_last_frame_at"] = status.get("last_frame_at")
        camera_data["online"] = self._compute_effective_online(camera_data)
        return camera_data

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
            "camera_ok",
            "mqtt_connected",
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
            "camera_ok",
            "mqtt_connected",
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

        light_mode = self._normalize_light_mode(
            source.get("light_state") or source.get("light_mode") or source.get("Light_Mode")
        )
        if light_mode:
            extra["light_state"] = light_mode   # field chuẩn mới
            extra["light_mode"]  = light_mode   # backward compat

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

    def _compute_effective_online(self, camera: Dict[str, Any]) -> bool:
        if camera.get("stream_connected"):
            return True
        return self._is_recent_timestamp(camera.get("last_seen_at"))

    def _is_recent_timestamp(self, value: Any) -> bool:
        if value in (None, ""):
            return False

        timestamp: Optional[datetime] = None
        if isinstance(value, datetime):
            timestamp = value
        else:
            raw = str(value).strip()
            if not raw:
                return False
            try:
                timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return False

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        return age <= max(1, int(self._settings.camera_status_ttl_seconds))

    @staticmethod
    def _normalize_light_mode(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        normalized = str(value).strip().lower()
        if normalized in {"red", "yellow", "green"}:
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
    def _is_placeholder_scalar(value: Optional[Any]) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in {
            "", "string", "null", "none", "-", "--", "n/a", "na", "unknown", 
            "undefined", "none", "[null]", "chưa cấu hình", "default"
        }

    def _has_reliable_device_identity(self, tb_device_name: Optional[str], runtime: Dict[str, Any]) -> bool:
        if not self._is_placeholder_scalar(tb_device_name):
            return True

        mac_address = runtime.get("mac_address")
        if not self._is_placeholder_scalar(mac_address):
            return True

        stream_url = runtime.get("stream_url")
        stream_host = runtime.get("stream_host") or runtime.get("ip_address")
        return not self._is_placeholder_scalar(stream_url) or not self._is_placeholder_scalar(stream_host)

    @staticmethod
    def _publish_camera_event(
        *,
        event_type: str,
        camera_id: int,
        tb_device_name: Optional[str] = None,
    ) -> None:
        # Không còn SSE web — chỉ log để debug
        logger.debug(
            "[EVENT] %s | cam=%s | tb=%s",
            event_type, camera_id, tb_device_name
        )

    def _get_cached_camera_list(self) -> Optional[List[Dict[str, Any]]]:
        with self._camera_list_cache_lock:
            if time.monotonic() >= self._camera_list_cache_until:
                return None
            return [dict(camera) for camera in self._camera_list_cache]

    def _set_cached_camera_list(self, cameras: List[Dict[str, Any]]) -> None:
        with self._camera_list_cache_lock:
            self._camera_list_cache = [dict(camera) for camera in cameras]
            self._camera_list_cache_until = time.monotonic() + self._camera_list_cache_ttl_seconds

    def _set_last_known_camera_list(self, cameras: List[Dict[str, Any]]) -> None:
        with self._camera_list_cache_lock:
            self._last_known_camera_list = [dict(camera) for camera in cameras]
            self._last_known_camera_list_at = time.monotonic()

    def _get_last_known_camera_list(self) -> Optional[List[Dict[str, Any]]]:
        with self._camera_list_cache_lock:
            if not self._last_known_camera_list:
                return None
            if time.monotonic() - self._last_known_camera_list_at > self._camera_list_grace_seconds:
                return None

        if not self._has_active_stream_workers():
            return None

        stream_status_map = self._get_stream_status_map()
        with self._camera_list_cache_lock:
            snapshot = [dict(camera) for camera in self._last_known_camera_list]

        return [
            self._attach_stream_status(
                dict(camera),
                stream_status_map.get(int(camera["camera_id"])) if camera.get("camera_id") is not None else None,
            )
            for camera in snapshot
            if camera.get("camera_id") is not None
        ]

    @staticmethod
    def _has_active_stream_workers() -> bool:
        # Stream workers không còn dùng trong Qt app
        return False

    def _invalidate_camera_list_cache(self) -> None:
        with self._camera_list_cache_lock:
            self._camera_list_cache = []
            self._camera_list_cache_until = 0.0
