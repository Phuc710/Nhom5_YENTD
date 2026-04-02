"""
Mosquitto MQTT Consumer — Backend nhận telemetry realtime từ ESP32.

Kiến trúc chuẩn (Production):
┌─────────────┐  MQTT :1883  ┌──────────────┐
│   ESP32-S3  │─────────────▶│  ThingsBoard  │  device mgmt, dashboard, RPC
│             │  MQTT :1888  ├──────────────┤
│             │─────────────▶│  Mosquitto    │◀── Backend subscribe (module này)
└─────────────┘              └──────────────┘

Vì web client (frontend) thường dùng REST Poll, còn Backend (luồng AI) 
cần độ trễ cực thấp (realtime) nên ESP32 sẽ tách làm 2 nhánh MQTT.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from backend.config.settings import get_settings
from backend.services.live_view_service import live_view_store
from backend.utils.logger import get_logger

logger = get_logger(__name__)

_settings = get_settings()

SUBSCRIBE_TOPIC  = "ytd/cameras/+/telemetry"
RECONNECT_BASE   = 2.0
RECONNECT_MAX    = 30.0
VALID_STATES     = {"red", "yellow", "green"}

class MosquittoConsumer:
    def __init__(self) -> None:
        self._running    = False
        self._task:      Optional[asyncio.Task] = None
        self._host       = _settings.mqtt_host
        self._port       = _settings.mqtt_port
        self._name_to_cam: Dict[str, int] = {}
        self._messages_received = 0
        self._reconnect_count   = 0
        self._last_error:    Optional[str] = None
        self._last_error_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(self._host)

    def update_identity_cache(self, name_to_cam: Dict[str, int]) -> None:
        self._name_to_cam = dict(name_to_cam)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="mosquitto_consumer")
        logger.info(
            "🟢 [MQTT] Khởi động nhận realtime từ ESP32 | broker=%s:%s",
            self._host, self._port,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️  [MQTT] MosquittoConsumer đã dừng")

    async def _run_loop(self) -> None:
        delay = RECONNECT_BASE
        while self._running:
            try:
                await self._connect_and_subscribe()
                delay = RECONNECT_BASE
                self._reconnect_count += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break
                error_text = f"{type(exc).__name__}: {exc}"
                if self._should_log_error(error_text):
                    logger.warning(
                        "⚠️ [MQTT] Mất kết nối Mosquitto (lần %s), thử lại sau %.0fs: %s",
                        self._reconnect_count, delay, error_text,
                    )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)
                self._reconnect_count += 1

    async def _connect_and_subscribe(self) -> None:
        import aiomqtt
        async with aiomqtt.Client(
            hostname=self._host,
            port=self._port,
            client_id="ytd-backend-consumer",  # aiomqtt 1.x dùng client_id, không phải identifier
            keepalive=30,
        ) as client:
            logger.info("✅ [MQTT] Đã kết nối Mosquitto thành công")
            self._last_error = None
            await client.subscribe(SUBSCRIBE_TOPIC, qos=1)
            async for message in client.messages:  # aiomqtt 1.x: iterate trực tiếp, không dùng context manager
                if not self._running:
                    return
                try:
                    await self._handle_message(str(message.topic), message.payload)
                except Exception:
                    pass

    async def _handle_message(self, topic: str, payload: bytes) -> None:
        self._messages_received += 1
        parts = topic.split("/")
        if len(parts) != 4:
            return

        device_name = parts[2]
        camera_id = self._name_to_cam.get(device_name)
        if camera_id is None:
            camera_id = self._lazy_resolve_camera_id(device_name)
            if camera_id is None:
                return

        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        raw_light = data.get("light_state") or data.get("Light_Mode") or data.get("light_mode") or ""
        light_state = self._normalize_light(raw_light)
        remain_sec = self._coerce_int(data.get("remain_sec")) or 0

        if light_state:
            live_view_store.update_runtime(
                camera_id,
                traffic_light_state=light_state,
                operation_mode="mqtt",
                tl_state_ms=remain_sec * 1000,
            )

    def _lazy_resolve_camera_id(self, device_name: str) -> Optional[int]:
        try:
            from backend.repositories.camera_repository import CameraRepository
            repo = CameraRepository()
            cameras = repo.get_all()
            for cam in cameras:
                if cam.get("tb_device_name") == device_name:
                    cid = int(cam["camera_id"])
                    self._name_to_cam[device_name] = cid
                    return cid
        except Exception:
            pass
        return None

    @staticmethod
    def _normalize_light(raw: Any) -> Optional[str]:
        if not raw:
            return None
        n = str(raw).strip().lower()
        return n if n in VALID_STATES else None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _should_log_error(self, error_text: str) -> bool:
        now = time.monotonic()
        if error_text != self._last_error or (now - self._last_error_at) >= 30.0:
            self._last_error = error_text
            self._last_error_at = now
            return True
        return False

tb_light_consumer = MosquittoConsumer()
