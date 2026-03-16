"""
StreamWorker — kéo MJPEG stream từ ESP32-S3 về và đẩy frame vào ViolationEngine.

ESP32-S3 phát stream tại: http://<ip>:81/stream
Format: multipart/x-mixed-replace;boundary=frame

Header mỗi part:
    --frame\r\n
    Content-Type: image/jpeg\r\n
    Content-Length: <N>\r\n
    \r\n
    <JPEG bytes>

Thiết kế "nhẹ nhất có thể":
- httpx.AsyncClient stream=True để đọc MJPEG chunk-by-chunk
- Parser multipart chuẩn, không lùng sục SOI/EOI markers
- Content-Length để cắt chính xác, lấy đúng JPEG không dư thiếu
- Gate detect: chỉ nhận xử lý khi đèn đỏ ổn định (ViolationEngine tự quyết)
- Throttle: tối đa MAX_FPS frame/s để tránh quá tải CPU/GPU
- Tự reconnect với exponential backoff
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import AsyncIterator, ClassVar, Optional

import cv2
import numpy as np

from backend.database.models import TrafficLightState
from backend.repositories.camera_repository import CameraRepository
from backend.services.live_view_service import live_view_store
from backend.services.violation_engine import ViolationEngine
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────── Cấu hình stream ────────────────────────────────────────

MAX_FPS = 8           # xử lý tối đa 8 frame/s (< FPS stream thực của camera)
RECONNECT_BASE = 2.0  # giây chờ cơ bản khi reconnect
RECONNECT_MAX = 10.0  # giây chờ tối đa để hệ thống tự bám lại nhanh trong 5-10s
STREAM_TIMEOUT_CONNECT = 4.0
STREAM_TIMEOUT_READ = 8.0

# MJPEG multipart
_BOUNDARY_RE = re.compile(rb"--frame\r?\n(.*?)\r?\n\r?\n", re.DOTALL)
_CONTENT_LEN_RE = re.compile(rb"Content-Length:\s*(\d+)", re.IGNORECASE)
_CHUNK_SIZE = 8192     # bytes per httpx chunk read


class StreamWorker:
    """
    Worker async cho 1 camera: kéo MJPEG stream → decode frame → ViolationEngine.

    Vòng lặp chính:
        while running:
            try:
                read MJPEG multipart stream from ESP32
                for each part:
                    extract Content-Length
                    read exactly N bytes of JPEG
                    decode + throttle + engine.process_frame()
            except:
                backoff → reconnect
    """

    _active_workers: ClassVar[dict[int, "StreamWorker"]] = {}
    _instance_seq: ClassVar[int] = 0

    def __init__(self, camera_id: int, stream_url: str) -> None:
        type(self)._instance_seq += 1
        self.instance_id = type(self)._instance_seq
        self.camera_id = camera_id
        self.stream_url = stream_url
        self._engine = ViolationEngine(camera_id)
        self._camera_repo = CameraRepository()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._process_task: Optional[asyncio.Task] = None
        self._connected = False
        self._reconnect_count = 0
        self._last_error: Optional[str] = None
        self._last_connected_at: Optional[datetime] = None
        self._last_frame_at: Optional[datetime] = None
        self._frame_interval = 1.0 / MAX_FPS   # giây giữa 2 lần process

    # ─────────────────────────────── Lifecycle ───────────────────────────────

    def start(self) -> None:
        if self._running:
            return

        previous = self._active_workers.get(self.camera_id)
        if previous and previous is not self:
            previous._running = False
            previous._connected = False
            if previous._process_task and not previous._process_task.done():
                previous._process_task.cancel()
            if previous._task and not previous._task.done():
                previous._task.cancel()
            logger.warning(
                "♻️ Thu hồi worker cũ | Cam: %s | old_worker=%s | new_worker=%s",
                self.camera_id,
                previous.instance_id,
                self.instance_id,
            )

        self._active_workers[self.camera_id] = self
        self._running = True
        self._task = asyncio.create_task(
            self._run_loop(), name=f"stream_worker_cam{self.camera_id}"
        )
        logger.info(
            "▶️  StreamWorker khởi động | Cam: %s | Worker: %s | URL: %s",
            self.camera_id,
            self.instance_id,
            self.stream_url,
        )

    async def stop(self) -> None:
        self._running = False
        self._connected = False
        if self._process_task and not self._process_task.done():
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        current = self._active_workers.get(self.camera_id)
        if current is self:
            self._active_workers.pop(self.camera_id, None)
        logger.info("⏹️  StreamWorker đã dừng | Cam: %s | Worker: %s", self.camera_id, self.instance_id)

    async def reload_zones(self) -> None:
        """Tải lại zones vào engine — gọi sau khi user lưu zones từ web UI."""
        zones = self._camera_repo.get_zones(self.camera_id)
        self._engine.load_zones(zones)
        logger.info("🔄 Reload zones | Cam: %s | count=%s", self.camera_id, len(zones))

    @property
    def is_running(self) -> bool:
        return self._running and (self._task is not None and not self._task.done())

    @property
    def is_connected(self) -> bool:
        return self.is_running and self._connected

    def status(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "running": self.is_running,
            "connected": self.is_connected,
            "stream_url": self.stream_url,
            "retry_count": self._reconnect_count,
            "last_error": self._last_error,
            "last_connected_at": self._last_connected_at,
            "last_frame_at": self._last_frame_at,
        }

    # ─────────────────────────────── Main Loop ───────────────────────────────

    async def _run_loop(self) -> None:
        try:
            while self._running:
                try:
                    await self._load_zones()
                    await self._stream_loop()
                    self._reconnect_count = 0
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    if not self._running:
                        break
                    self._connected = False
                    self._last_error = str(exc)
                    delay = min(RECONNECT_BASE * (2 ** min(self._reconnect_count, 5)), RECONNECT_MAX)
                    self._reconnect_count += 1
                    logger.warning(
                        "⚠️ Stream cam=%s lỗi (worker=%s, lần %s), thử lại sau %.0fs: %s",
                        self.camera_id,
                        self.instance_id,
                        self._reconnect_count,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
        finally:
            current = self._active_workers.get(self.camera_id)
            if current is self:
                self._active_workers.pop(self.camera_id, None)

    async def _load_zones(self) -> None:
        try:
            zones = self._camera_repo.get_zones(self.camera_id)
            self._engine.load_zones(zones)
        except Exception as exc:
            logger.warning("⚠️ Không đọc được zones cam=%s: %s", self.camera_id, exc)

    async def _stream_loop(self) -> None:
        """Đọc MJPEG multipart stream và xử lý từng JPEG part."""
        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=STREAM_TIMEOUT_CONNECT,
                read=STREAM_TIMEOUT_READ,
                write=10.0,
                pool=None,
            ),
            follow_redirects=True,
        ) as client:
            logger.info(
                "🔗 Đang kết nối stream | Cam: %s | Worker: %s | %s",
                self.camera_id,
                self.instance_id,
                self.stream_url,
            )

            try:
                async with client.stream(
                    "GET",
                    self.stream_url,
                    headers={"Accept": "multipart/x-mixed-replace, image/jpeg"},
                ) as response:
                    response.raise_for_status()
                    self._connected = True
                    self._reconnect_count = 0
                    self._last_error = None
                    self._last_connected_at = datetime.now(timezone.utc)
                    logger.info(
                        "✅ Kết nối stream thành công | Cam: %s | Worker: %s",
                        self.camera_id,
                        self.instance_id,
                    )
                    self._camera_repo.touch_last_seen(self.camera_id)

                    last_process_time = 0.0
                    async for jpeg_bytes in self._iter_mjpeg_parts(response):
                        if not self._running:
                            return

                        self._last_frame_at = datetime.now(timezone.utc)

                        # Đưa thẳng frame RAW vào cache ngay lập tức để Web Stream xem với max FPS của ESP32
                        live_view_store.update_jpeg(self.camera_id, jpeg_bytes)

                        # Throttle FPS riêng cho AI Engine để không bị cháy CPU server
                        now = time.monotonic()
                        if now - last_process_time < self._frame_interval:
                            continue
                        last_process_time = now

                        if self._process_task is None or self._process_task.done():
                            self._process_task = asyncio.create_task(
                                self._process_frame_safe(jpeg_bytes),
                                name=f"stream_ai_cam{self.camera_id}",
                            )
            finally:
                self._connected = False

    async def _iter_mjpeg_parts(self, response) -> AsyncIterator[bytes]:
        """
        Generator parse MJPEG multipart stream từ httpx streaming response.

        Protocol ESP32 stream_server.c:
            --frame\r\n
            Content-Type: image/jpeg\r\n
            Content-Length: N\r\n
            \r\n
            <N bytes of JPEG>
        """
        buffer = b""
        body_remaining = 0   # số byte JPEG còn cần đọc
        body_parts: list[bytes] = []

        async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
            buffer += chunk

            while True:
                if body_remaining > 0:
                    # Đang trong body (JPEG bytes)
                    take = min(body_remaining, len(buffer))
                    body_parts.append(buffer[:take])
                    buffer = buffer[take:]
                    body_remaining -= take

                    if body_remaining == 0:
                        # Hoàn thành 1 JPEG part
                        yield b"".join(body_parts)
                        body_parts = []
                else:
                    # Tìm header part: --frame\r\n...\r\n\r\n
                    sep = buffer.find(b"\r\n\r\n")
                    if sep == -1:
                        break  # chưa đủ data, đọc chunk tiếp theo

                    header_block = buffer[:sep]
                    buffer = buffer[sep + 4:]  # bỏ qua \r\n\r\n

                    # Tìm Content-Length trong header
                    m = _CONTENT_LEN_RE.search(header_block)
                    if m:
                        body_remaining = int(m.group(1))
                        body_parts = []
                    # Nếu không có Content-Length → bỏ qua part này
                    break

    # ─────────────────────────────── Frame Processing ────────────────────────

    async def _process_frame(self, jpeg_bytes: bytes) -> None:
        frame = _decode_jpeg(jpeg_bytes)
        if frame is None:
            return

        timestamp = datetime.now(timezone.utc)
        light_state = self._read_light_state()

        # Cập nhật live view (stream frame mới nhất)
        live_view_store.update_frame(
            self.camera_id,
            timestamp=timestamp,
            frame_width=int(frame.shape[1]),
            frame_height=int(frame.shape[0]),
            traffic_light_state=light_state.value,
            operation_mode="stream",
            tl_state_ms=0,
            quality_score=0.0,
            processing_ms=0,
            detections=[],
            jpeg_bytes=jpeg_bytes,
        )

        # Đưa frame vào ViolationEngine (sẽ tự gate detect theo đèn đỏ)
        await self._engine.process_frame(frame, light_state, timestamp)

    async def _process_frame_safe(self, jpeg_bytes: bytes) -> None:
        try:
            await self._process_frame(jpeg_bytes)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("⚠️ Lỗi xử lý frame cam=%s: %s", self.camera_id, exc)

    def _read_light_state(self) -> TrafficLightState:
        """Đọc trạng thái đèn hiện tại từ live_view_store (được cập nhật qua ThingsBoard MQTT heartbeat)."""
        overlay = live_view_store.get_state(self.camera_id)
        if not overlay:
            return TrafficLightState.RED  # default an toàn

        raw = str(overlay.get("traffic_light_state") or "").strip().lower()
        try:
            return TrafficLightState(raw)
        except ValueError:
            return TrafficLightState.RED


# ───────────────────────── Utility ────────────────────────────────────────────

def _decode_jpeg(data: bytes) -> Optional[np.ndarray]:
    """Decode JPEG bytes thành BGR numpy array. Trả về None nếu lỗi."""
    try:
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame
    except Exception:
        return None
