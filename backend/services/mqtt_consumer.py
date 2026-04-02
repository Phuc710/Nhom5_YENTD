"""
MQTT Consumer — Backend subscribe telemetry realtime từ Mosquitto.

Kiến trúc dual-MQTT:
┌─────────────┐
│   ESP32-S3  │──── MQTT :1883 ──▶ ThingsBoard  (device mgmt, dashboard, RPC)
│             │──── MQTT :1888 ──▶ Mosquitto ◀── Backend subscribe (module này)
└─────────────┘

ESP32 publish 2 topic song song:
  - ThingsBoard : v1/devices/me/telemetry   (standard TB protocol, dùng device token)
  - Mosquitto   : cameras/{name}/telemetry  (custom, backend đọc)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any, Dict, Optional

from backend.config.settings import get_settings
from backend.services.live_view_service import live_view_store
from backend.utils.logger import get_logger

logger = get_logger(__name__)

_settings = get_settings()

# Topic ESP32 publish lên Mosquitto
SUBSCRIBE_TOPIC = "cameras/+/telemetry"
VALID_STATES    = {"red", "yellow", "green"}
RECONNECT_BASE  = 2.0
RECONNECT_MAX   = 30.0


class MqttConsumer:
    """Subscribe Mosquitto, cập nhật live_view_store khi ESP32 gửi telemetry."""

    def __init__(self) -> None:
        self._host    = _settings.mqtt_host
        self._port    = _settings.mqtt_port
        self._running = False
        self._task:   Optional[asyncio.Task] = None
        self._client: Any = None
        # Cache device_name → camera_id để tránh query DB mỗi message
        self._name_to_cam: Dict[str, int] = {}
        # Tránh spam log cùng 1 lỗi
        self._last_err:    Optional[str] = None
        self._last_err_at: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Trả True nếu MQTT_HOST đã được set trong .env."""
        return bool(self._host)

    def update_identity_cache(self, name_to_cam: Dict[str, int]) -> None:
        """CameraService gọi khi có thay đổi device list."""
        self._name_to_cam = dict(name_to_cam)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="mqtt_consumer")
        logger.info(
            "🟢 [MQTT] Consumer khởi động | broker=%s:%s | topic=%s",
            self._host, self._port, SUBSCRIBE_TOPIC,
        )

    async def stop(self) -> None:
        self._running = False
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.__aexit__(None, None, None)
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=3.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
        logger.info("⏹️  [MQTT] Consumer đã dừng")

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        delay = RECONNECT_BASE
        attempt = 0
        while self._running:
            try:
                await self._connect_and_consume()
                delay = RECONNECT_BASE  # reset sau khi kết nối thành công
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break
                err = f"{type(exc).__name__}: {exc}"
                if self._should_log(err):
                    attempt += 1
                    logger.warning(
                        "⚠️ [MQTT] Mất kết nối (lần %d), thử lại sau %.0fs: %s",
                        attempt, delay, err,
                    )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)

    async def _connect_and_consume(self) -> None:
        import aiomqtt
        client = aiomqtt.Client(
            hostname=self._host,
            port=self._port,
            identifier="backend",
            keepalive=30,
        )
        async with client:
            self._client = client
            logger.info("✅ [MQTT] Đã kết nối Mosquitto %s:%d", self._host, self._port)
            self._last_err = None
            try:
                await client.subscribe(SUBSCRIBE_TOPIC, qos=1)
                async for message in client.messages:
                    if not self._running:
                        return
                    try:
                        self._handle(str(message.topic), bytes(message.payload))
                    except Exception:
                        pass  # không để 1 message lỗi crash toàn consumer
            finally:
                self._client = None

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    def _handle(self, topic: str, payload: bytes) -> None:
        # topic format: cameras/{device_name}/telemetry
        parts = topic.split("/")
        if len(parts) != 4:
            return

        device_name = parts[2]
        camera_id   = self._resolve_camera_id(device_name)
        if camera_id is None:
            return

        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Hỗ trợ nhiều key name khác nhau từ firmware
        raw_light = (
            data.get("light_state")
            or data.get("Light_Mode")
            or data.get("light_mode")
            or ""
        )
        light = self._normalize_light(raw_light)
        remain_ms = (self._to_int(data.get("remain_sec")) or 0) * 1000

        if light:
            icon = "🔴" if light == "red" else "🟡" if light == "yellow" else "🟢"
            sec = remain_ms // 1000
            logger.info(
                "📥 [MQTT] Payload | %s | %s %s (%ds)",
                device_name, icon, light.upper(), sec
            )
            
            live_view_store.update_runtime(
                camera_id,
                traffic_light_state=light,
                operation_mode="mqtt",
                tl_state_ms=remain_ms,
            )

    def _resolve_camera_id(self, device_name: str) -> Optional[int]:
        """Tìm camera_id từ cache, nếu không có thì query DB 1 lần."""
        cached = self._name_to_cam.get(device_name)
        if cached is not None:
            return cached
        try:
            from backend.repositories.camera_repository import CameraRepository
            for cam in CameraRepository().get_all():
                if cam.get("tb_device_name") == device_name:
                    cid = int(cam["camera_id"])
                    self._name_to_cam[device_name] = cid
                    return cid
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_light(raw: Any) -> Optional[str]:
        if not raw:
            return None
        val = str(raw).strip().lower()
        return val if val in VALID_STATES else None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _should_log(self, err: str) -> bool:
        now = time.monotonic()
        if err != self._last_err or (now - self._last_err_at) >= 30.0:
            self._last_err    = err
            self._last_err_at = now
            return True
        return False


# Singleton — dùng trong main.py
mqtt_consumer = MqttConsumer()
