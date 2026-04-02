"""
StreamWorker — Kiến trúc 2 luồng song song (Production-Grade).

┌──────────────────────────────────────────────────────────────┐
│                    LUỒNG A: STREAM (Full FPS)                │
│  Đọc MJPEG liên tục → Update web live view ngay lập tức     │
│  Không throttle — chạy hết tốc độ của ESP32 (10-30 FPS)     │
│  Kết quả: Live view mượt, không giật                        │
└──────────────────────────────────────────────────────────────┘
          │  Lưu frame mới nhất vào _latest_frame buffer
          ▼
┌──────────────────────────────────────────────────────────────┐
│                    LUỒNG B: AI (Throttled)                  │
│  Cứ 120ms lấy frame MỚI NHẤT từ buffer đẩy vào engine      │
│  5-8 FPS cho ViolationEngine → Không quá tải CPU/GPU        │
│  Chạy song song, KHÔNG block Luồng A                        │
└──────────────────────────────────────────────────────────────┘

Thiết kế:
- httpx.AsyncClient stream=True để đọc MJPEG chunk-by-chunk
- Parser multipart chuẩn với Content-Length — không lùng sục SOI/EOI
- AI loop dùng asyncio.Event để tránh busy-wait
- Exponential backoff khi reconnect (2s → 10s max)
- Config refresh 10s/lần (camera orientation, threshold)
"""
from __future__ import annotations

import asyncio
import re
import time
import threading
from datetime import datetime, timezone
from typing import AsyncIterator, ClassVar, Optional

import cv2
import numpy as np

from backend.config.settings import get_settings
from backend.database.models import TrafficLightState
from backend.repositories.camera_repository import CameraRepository
from backend.services.live_view_service import live_view_store
from backend.services.realtime_service import realtime_service
from backend.services.violation_engine import ViolationEngine
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────── Cấu hình stream ────────────────────────────────────────

AI_FPS         = 8            # Luồng B: tối đa N frame/s cho AI
AI_INTERVAL    = 1.0 / AI_FPS # 125ms giữa 2 frame AI

RECONNECT_BASE = 2.0          # giây chờ cơ bản khi reconnect
RECONNECT_MAX  = 10.0         # giây chờ tối đa

STREAM_TIMEOUT_CONNECT = 4.0
STREAM_TIMEOUT_READ    = 8.0
SNAPSHOT_TIMEOUT       = 8.0

# MJPEG multipart
_BOUNDARY_RE     = re.compile(rb"--frame\r?\n(.*?)\r?\n\r?\n", re.DOTALL)
_CONTENT_LEN_RE  = re.compile(rb"Content-Length:\s*(\d+)", re.IGNORECASE)
_CHUNK_SIZE      = 8192        # bytes per httpx chunk
_settings        = get_settings()


# ─────────────────── Latest Frame Buffer (thread-safe) ─────────────────────

class _FrameBuffer:
    """Buffer lưu frame JPEG mới nhất + signal cho AI loop."""

    __slots__ = ("_jpeg", "_lock", "_event", "_ts")

    def __init__(self) -> None:
        self._jpeg: Optional[bytes] = None
        self._lock  = threading.Lock()
        self._event = asyncio.Event()  # signal: "có frame mới rồi"
        self._ts: float = 0.0

    def put(self, jpeg: bytes) -> None:
        """Stream loop gọi: lưu frame mới nhất."""
        with self._lock:
            self._jpeg = jpeg
            self._ts   = time.monotonic()
        # Wake AI loop nếu đang đợi
        try:
            self._event.set()
        except RuntimeError:
            pass  # không có event loop (unit test)

    def get_latest(self) -> Optional[bytes]:
        """AI loop gọi: lấy frame mới nhất (hoặc None nếu chưa có)."""
        with self._lock:
            return self._jpeg

    async def wait_for_new(self, timeout: float = 1.0) -> bool:
        """AI loop đợi đến khi có frame mới. Trả về True nếu có frame."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            self._event.clear()
            return True
        except asyncio.TimeoutError:
            return False


# ─────────────────────────────── StreamWorker ────────────────────────────────

class StreamWorker:
    """
    Worker async cho 1 camera: kéo MJPEG → live view + AI pipeline.

    Kiến trúc 2 luồng:
        Task 1: _stream_loop() → đọc MJPEG, update live_view_store (full FPS)
        Task 2: _ai_loop()     → throttled AI processing (AI_FPS)
    """

    _active_workers: ClassVar[dict[int, "StreamWorker"]] = {}
    _instance_seq:   ClassVar[int] = 0

    def __init__(self, camera_id: int, stream_url: str) -> None:
        type(self)._instance_seq += 1
        self.instance_id = type(self)._instance_seq
        self.camera_id   = camera_id
        self.stream_url  = stream_url

        self._engine       = ViolationEngine(camera_id)
        self._camera_repo  = CameraRepository()
        self._frame_buffer = _FrameBuffer()

        # Lifecycle
        self._running   = False
        self._connected = False
        self._stream_task:  Optional[asyncio.Task] = None
        self._ai_task:      Optional[asyncio.Task] = None

        # Stats
        self._reconnect_count           = 0
        self._last_error:               Optional[str]      = None
        self._last_connected_at:        Optional[datetime] = None
        self._last_frame_at:            Optional[datetime] = None
        self._frames_received:          int  = 0
        self._frames_processed_by_ai:   int  = 0

        # Error dedup logging
        self._last_logged_stream_error:    Optional[str] = None
        self._last_logged_stream_error_at: float = 0.0
        self._last_logged_ai_error:        Optional[str] = None
        self._last_logged_ai_error_at:     float = 0.0

        # Snapshot mode
        self._stream_mode      = _settings.stream_capture_mode
        self._snapshot_url     = self._build_snapshot_url(stream_url)
        self._snapshot_interval = max(0.2, float(_settings.stream_snapshot_interval_ms) / 1000.0)

        # Camera config cache (orientation, confidence threshold...)
        self._camera_config:         Optional[dict] = None
        self._last_config_refresh:   float = 0.0
        self._config_refresh_interval = 10.0  # seconds

    # ─────────────────────────────── Lifecycle ───────────────────────────────

    def start(self) -> None:
        """Khởi động worker: tạo 2 task song song."""
        if self._running:
            return

        # Thu hồi worker cũ nếu có
        previous = self._active_workers.get(self.camera_id)
        if previous and previous is not self:
            previous._running = False
            previous._connected = False
            for task in (previous._ai_task, previous._stream_task):
                if task and not task.done():
                    task.cancel()
            logger.warning(
                "♻️ [Worker] Thu hồi worker cũ | Cam: %s | cũ=%s → mới=%s",
                self.camera_id, previous.instance_id, self.instance_id,
            )

        self._active_workers[self.camera_id] = self
        self._running = True

        # Task 1: Stream loop (full FPS, no throttle)
        self._stream_task = asyncio.create_task(
            self._stream_run_loop(),
            name=f"stream_cam{self.camera_id}",
        )
        # Task 2: AI loop (throttled)
        self._ai_task = asyncio.create_task(
            self._ai_run_loop(),
            name=f"ai_cam{self.camera_id}",
        )

        logger.info(
            "▶️  [Worker] Khởi động | Cam: %s | Worker: %s | Mode: %s | URL: %s",
            self.camera_id, self.instance_id,
            self._stream_mode, self.stream_url,
        )

    async def stop(self) -> None:
        """Dừng cả 2 task."""
        self._running   = False
        self._connected = False

        tasks = [t for t in (self._ai_task, self._stream_task) if t and not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self._active_workers.get(self.camera_id) is self:
            self._active_workers.pop(self.camera_id, None)

        logger.info(
            "⏹️  [Worker] Đã dừng | Cam: %s | Worker: %s | "
            "frames_recv=%s ai_proc=%s",
            self.camera_id, self.instance_id,
            self._frames_received, self._frames_processed_by_ai,
        )

    async def reload_zones(self) -> None:
        """Hot-reload zones từ DB vào engine (gọi sau khi user lưu zones)."""
        zones = self._camera_repo.get_zones(self.camera_id)
        self._engine.load_zones(zones)
        logger.info(
            "🔄 [Worker] Reload zones | Cam: %s | count=%s",
            self.camera_id, len(zones),
        )

    # ── Properties ──

    @property
    def is_running(self) -> bool:
        return self._running and bool(
            self._stream_task and not self._stream_task.done()
        )

    @property
    def is_connected(self) -> bool:
        return self.is_running and self._connected

    def status(self) -> dict:
        return {
            "camera_id":          self.camera_id,
            "running":            self.is_running,
            "connected":          self.is_connected,
            "stream_url":         self.stream_url,
            "retry_count":        self._reconnect_count,
            "last_error":         self._last_error,
            "last_connected_at":  self._last_connected_at,
            "last_frame_at":      self._last_frame_at,
            "frames_received":    self._frames_received,
            "frames_ai_processed":self._frames_processed_by_ai,
        }

    # ─────────────────── LUỒNG A: Stream Run Loop ────────────────────────────

    async def _stream_run_loop(self) -> None:
        """
        Luồng A — Kết nối + đọc stream, tự reconnect khi lỗi.
        Chỉ làm 2 việc: đọc JPEG → cập nhật web live view (full FPS).
        """
        try:
            while self._running:
                try:
                    await self._load_zones()
                    if self._stream_mode == "snapshot":
                        await self._snapshot_loop()
                    else:
                        await self._mjpeg_loop()
                    self._reconnect_count = 0
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    if not self._running:
                        break
                    self._connected = False
                    error_text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                    self._last_error = error_text
                    delay = min(RECONNECT_BASE * (2 ** min(self._reconnect_count, 5)), RECONNECT_MAX)
                    self._reconnect_count += 1
                    if self._should_log_error(error_text, kind="stream"):
                        logger.warning(
                            "⚠️ [Stream] Cam %s lỗi (lần %s), thử lại sau %.0fs: %s",
                            self.camera_id, self._reconnect_count, delay, error_text,
                        )
                    await asyncio.sleep(delay)
        finally:
            if self._active_workers.get(self.camera_id) is self:
                self._active_workers.pop(self.camera_id, None)

    async def _mjpeg_loop(self) -> None:
        """
        Đọc MJPEG multipart từ ESP32.
        Mỗi JPEG frame nhận được:
          1. Lưu vào _frame_buffer (signal AI loop)
          2. Đẩy thẳng vào live_view_store cho web (KHÔNG throttle)
        """
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
                "🔗 [Stream] Kết nối | Cam: %s | Worker: %s | %s",
                self.camera_id, self.instance_id, self.stream_url,
            )
            async with client.stream(
                "GET",
                self.stream_url,
                headers={"Accept": "multipart/x-mixed-replace, image/jpeg"},
            ) as response:
                response.raise_for_status()
                self._on_connected()

                async for jpeg_bytes in self._iter_mjpeg_parts(response):
                    if not self._running:
                        return

                    self._frames_received += 1
                    self._last_frame_at = datetime.now(timezone.utc)

                    # ① Cập nhật web live view NGAY LẬP TỨC (full FPS, no throttle)
                    live_view_store.update_jpeg(self.camera_id, jpeg_bytes)

                    # ② Cập nhật buffer để AI loop lấy
                    self._frame_buffer.put(jpeg_bytes)

    async def _snapshot_loop(self) -> None:
        """
        Poll /snapshot định kỳ (thay thế MJPEG cho camera không hỗ trợ streaming).
        Cứ snapshot_interval ms lấy 1 ảnh → update live view + AI buffer.
        """
        import httpx

        logger.info(
            "🔗 [Snapshot] Kết nối | Cam: %s | Worker: %s | %s",
            self.camera_id, self.instance_id, self._snapshot_url,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=STREAM_TIMEOUT_CONNECT,
                read=SNAPSHOT_TIMEOUT,
                write=10.0,
                pool=None,
            ),
            follow_redirects=True,
        ) as client:
            while self._running:
                response = None
                try:
                    response = await client.get(
                        self._snapshot_url,
                        headers={"Accept": "image/jpeg"},
                    )
                    response.raise_for_status()

                    if not self._connected:
                        self._on_connected()

                    jpeg_bytes = response.content
                    if not jpeg_bytes:
                        raise RuntimeError("Snapshot empty")

                    self._frames_received += 1
                    self._last_frame_at = datetime.now(timezone.utc)
                    live_view_store.update_jpeg(self.camera_id, jpeg_bytes)
                    self._frame_buffer.put(jpeg_bytes)

                    self._camera_repo.touch_last_seen(self.camera_id)
                    await asyncio.sleep(self._snapshot_interval)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise
                finally:
                    if response is not None:
                        await response.aclose()

    # ─────────────────── LUỒNG B: AI Run Loop ────────────────────────────────

    async def _ai_run_loop(self) -> None:
        """
        Luồng B — Throttled AI processing.
        Cứ AI_INTERVAL giây lấy frame MỚI NHẤT từ buffer và đẩy qua ViolationEngine.
        Chạy hoàn toàn độc lập với Luồng A — AI chậm không ảnh hưởng live view.
        """
        last_ai_time = 0.0

        while self._running:
            try:
                # Đợi frame mới từ buffer (max 1s)
                has_frame = await self._frame_buffer.wait_for_new(timeout=1.0)
                if not has_frame or not self._running:
                    continue

                # Throttle: kiểm tra đã đủ thời gian chưa
                now = time.monotonic()
                elapsed = now - last_ai_time
                if elapsed < AI_INTERVAL:
                    # Chưa đến lúc — đợi phần còn lại
                    await asyncio.sleep(AI_INTERVAL - elapsed)
                    if not self._running:
                        break

                # Lấy frame MỚI NHẤT (không phải frame lúc event fired)
                jpeg_bytes = self._frame_buffer.get_latest()
                if jpeg_bytes is None:
                    continue

                last_ai_time = time.monotonic()
                self._frames_processed_by_ai += 1

                # Process không block loop: chạy trong to_thread nếu cần
                await self._process_frame_safe(jpeg_bytes)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                if self._should_log_error(error_text, kind="ai"):
                    logger.warning(
                        "⚠️ [AI] Cam %s lỗi xử lý frame: %s",
                        self.camera_id, error_text,
                    )
                await asyncio.sleep(0.5)

        logger.debug("[AI] Loop kết thúc | Cam: %s", self.camera_id)

    # ─────────────────── Frame Processing ────────────────────────────────────

    async def _process_frame(self, jpeg_bytes: bytes) -> None:
        """Decode JPEG → ViolationEngine → update live view overlay."""
        frame = _decode_jpeg(jpeg_bytes)
        if frame is None:
            return

        await self._ensure_config()

        timestamp   = datetime.now(timezone.utc)
        light_state = self._read_light_state()

        detections = await self._engine.process_frame(
            frame, light_state, timestamp, config=self._camera_config
        )

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
            detections=detections or [],
        )

    async def _process_frame_safe(self, jpeg_bytes: bytes) -> None:
        """Wrapper an toàn để tránh crash AI loop."""
        try:
            await self._process_frame(jpeg_bytes)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            if self._should_log_error(error_text, kind="ai"):
                logger.warning(
                    "⚠️ [AI] Lỗi xử lý frame cam=%s: %s",
                    self.camera_id, error_text,
                )

    # ─────────────────── Helpers ─────────────────────────────────────────────

    def _on_connected(self) -> None:
        """Gọi khi kết nối stream thành công."""
        self._connected       = True
        self._reconnect_count = 0
        self._last_error      = None
        self._last_connected_at = datetime.now(timezone.utc)
        self._publish_stream_state_event(True)
        self._camera_repo.touch_last_seen(self.camera_id)
        logger.info(
            "✅ [Stream] Kết nối thành công | Cam: %s | Worker: %s",
            self.camera_id, self.instance_id,
        )

    async def _load_zones(self) -> None:
        try:
            zones = self._camera_repo.get_zones(self.camera_id)
            self._engine.load_zones(zones)
        except Exception as exc:
            logger.warning("⚠️ Không đọc được zones cam=%s: %s", self.camera_id, exc)

    async def _ensure_config(self) -> None:
        """Fetch/Refresh camera config mỗi 10s (orientation, confidence threshold)."""
        now = time.monotonic()
        if self._camera_config is not None and (now - self._last_config_refresh < self._config_refresh_interval):
            return
        try:
            cam_data = self._camera_repo.get_by_id(self.camera_id)
            if cam_data:
                self._camera_config      = cam_data
                self._last_config_refresh = now
        except Exception as exc:
            if self._camera_config is None:
                logger.warning("⚠️ Không đọc được config cam=%s: %s", self.camera_id, exc)

    def _read_light_state(self) -> TrafficLightState:
        """
        Đọc trạng thái đèn hiện tại từ live_view_store.
        live_view_store được cập nhật bởi:
          - MQTT ThingsBoard consumer (telemetry light_state từ ESP32)
          - HTTP heartbeat (fallback, nếu còn dùng)
        Mặc định an toàn: RED.
        """
        overlay = live_view_store.get_state(self.camera_id)
        if not overlay:
            return TrafficLightState.RED

        raw = str(overlay.get("traffic_light_state") or "").strip().lower()
        try:
            return TrafficLightState(raw)
        except ValueError:
            return TrafficLightState.RED

    def _publish_stream_state_event(self, connected: bool) -> None:
        realtime_service.publish(
            event_type="camera.stream_connected" if connected else "camera.stream_disconnected",
            resources=["cameras", "summary"],
            table="cameras",
            payload={
                "camera_id":      self.camera_id,
                "stream_connected": connected,
            },
        )

    @staticmethod
    def _build_snapshot_url(stream_url: str) -> str:
        normalized = (stream_url or "").strip()
        if normalized.endswith("/stream"):
            return normalized[:-7] + "/snapshot"
        if normalized.endswith("/snapshot"):
            return normalized
        return normalized.rstrip("/") + "/snapshot"

    def _should_log_error(self, error_text: str, *, kind: str) -> bool:
        """Dedup log: chỉ log lại nếu lỗi mới hoặc đã quá 15s kể từ lần log trước."""
        now = time.monotonic()
        if kind == "stream":
            last_err = self._last_logged_stream_error
            last_at  = self._last_logged_stream_error_at
        else:
            last_err = self._last_logged_ai_error
            last_at  = self._last_logged_ai_error_at

        should = error_text != last_err or (now - last_at) >= 15.0
        if not should:
            return False

        if kind == "stream":
            self._last_logged_stream_error    = error_text
            self._last_logged_stream_error_at = now
        else:
            self._last_logged_ai_error    = error_text
            self._last_logged_ai_error_at = now
        return True

    # ─────────────────── MJPEG Parser ────────────────────────────────────────

    async def _iter_mjpeg_parts(self, response) -> AsyncIterator[bytes]:
        """
        Parse MJPEG multipart stream từ httpx streaming response.
        Dùng Content-Length để cắt chính xác — không lùng sục SOI/EOI markers.
        Giới hạn frame size 500KB để tránh MemoryError.
        """
        buffer        = b""
        body_remaining = 0
        body_parts: list[bytes] = []
        MAX_FRAME_SIZE = 500_000  # 500KB

        async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
            buffer += chunk

            while True:
                if body_remaining > 0:
                    # Đang đọc body (JPEG bytes)
                    take = min(body_remaining, len(buffer))
                    body_parts.append(buffer[:take])
                    buffer = buffer[take:]
                    body_remaining -= take

                    if body_remaining == 0:
                        yield b"".join(body_parts)
                        body_parts = []
                else:
                    # Tìm header: --frame\r\n...\r\n\r\n
                    frame_start = buffer.find(b"--frame")
                    if frame_start > 0:
                        buffer = buffer[frame_start:]

                    sep = buffer.find(b"\r\n\r\n")
                    if sep == -1:
                        if len(buffer) > _CHUNK_SIZE * 2:
                            buffer = buffer[-_CHUNK_SIZE:]
                        break

                    header_block  = buffer[:sep]
                    buffer        = buffer[sep + 4:]

                    m = _CONTENT_LEN_RE.search(header_block)
                    if m:
                        try:
                            content_len = int(m.group(1))
                            if 0 < content_len < MAX_FRAME_SIZE:
                                body_remaining = content_len
                                body_parts     = []
                            else:
                                logger.warning(
                                    "⚠️ [Stream] Content-Length bất thường (%s), bỏ qua frame.",
                                    content_len,
                                )
                        except (ValueError, TypeError):
                            pass

                    if body_remaining == 0:
                        continue


# ─────────────────────────── Utility ─────────────────────────────────────────

def _decode_jpeg(data: bytes) -> Optional[np.ndarray]:
    """Decode JPEG bytes thành BGR numpy array. Trả về None nếu lỗi."""
    try:
        arr   = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame
    except Exception:
        return None
