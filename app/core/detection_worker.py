"""
DetectionWorker — AI loop chính cho PyQt5 app.

Flow đúng theo doc:
    StreamClientThread ──raw_frame──► DetectionWorker
    MqttClientThread   ──light_state──► DetectionWorker
        │
        └─► asyncio event loop (trong thread này)
                │
                ├─► ViolationEngine.process_frame()   ← state machine xanh/đỏ
                │       ├─ Đèn XANH: detect bbox only, mark was_before_line
                │       └─ Đèn ĐỎ ổn định: detect+OCR, check crossing, enqueue
                │
                └─► violation_queue ──► ViolationProcessor.run_loop()
                                            ├─ OCR vote
                                            ├─ upload ảnh (parallel)
                                            ├─ save DB
                                            └─ violation_saved signal → ViolationsPanel

Signals:
    detections_ready(list)   → StreamView.set_detections() (bbox overlay)
    violation_saved(dict)    → ViolationsPanel.on_violation() (thêm hàng)
    ai_fps_updated(float)    → Info panel
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

# Giới hạn FPS AI — đủ để detect xe, không chiếm CPU
_AI_FPS = 8
_AI_INTERVAL = 1.0 / _AI_FPS


class DetectionWorker(QThread):
    """
    Thread chính của AI loop. Chạy asyncio event loop bên trong
    để tương thích với ViolationEngine + ViolationProcessor (async).

    Bridge về Qt qua pyqtSignal (thread-safe).
    """

    detections_ready = pyqtSignal(list)   # bbox list → StreamView
    violation_saved  = pyqtSignal(dict)   # violation dict → ViolationsPanel
    ai_fps_updated   = pyqtSignal(float)  # FPS thực tế → UI

    def __init__(self, camera_id: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._camera_id    = camera_id
        self._running      = False

        # Zones từ StreamView (normalized 0..1)
        self._zones: Dict[str, Optional[np.ndarray]] = {
            "stop_line":   None,
            "detect_zone": None,
        }
        self._zones_dirty  = False   # cờ: zones thay đổi → reload engine

        # Frame queue (thread-safe, maxsize=1: luôn lấy frame mới nhất)
        self._frame_q: queue.Queue = queue.Queue(maxsize=1)

        # Light state (từ MQTT)
        self._light_state  = "GREEN"   # mặc định xanh khi chưa có MQTT

        # asyncio bridge (set khi loop chạy)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Public API (gọi từ UI thread) ──────────────────────────────────────────

    def set_camera_id(self, camera_id: int) -> None:
        self._camera_id = camera_id

    def set_zones(self, zones: Dict[str, Optional[np.ndarray]]) -> None:
        """Cập nhật zones từ StreamView. Thread-safe."""
        self._zones      = zones
        self._zones_dirty = True

    def on_frame(self, _qt_img, frame: np.ndarray) -> None:
        """Nhận raw frame từ StreamClientThread. Bỏ frame cũ nếu queue đầy."""
        try:
            self._frame_q.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_q.get_nowait()   # bỏ frame cũ
            except queue.Empty:
                pass
            try:
                self._frame_q.put_nowait(frame)
            except queue.Full:
                pass

    @pyqtSlot(str, str)
    def on_light_changed(self, _device: str, state: str) -> None:
        """Nhận light_state từ MqttClientThread. Thread-safe."""
        self._light_state = state.upper()

    def stop(self) -> None:
        self._running = False
        # Do not force loop.stop() to avoid 'Event loop stopped before Future completed'
        # The while self._running loop in _ai_loop will gracefully exit.

    # ── QThread run ────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        logger.info("DetectionWorker start cam=%s", self._camera_id)
        try:
            self._loop.run_until_complete(self._ai_loop())
        except Exception as exc:
            logger.error("DetectionWorker loop error: %s", exc)
        finally:
            try:
                # Chờ các task đang dở kết thúc (như upload ảnh)
                pending = asyncio.all_tasks(self._loop)
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            self._loop.close()
            logger.info("DetectionWorker stop cam=%s", self._camera_id)

    # ── Async AI loop ──────────────────────────────────────────────────────────

    async def _ai_loop(self) -> None:
        """Vòng lặp chính: khởi tạo engine + processor, rồi process từng frame."""
        from backend.services.violation_engine import ViolationEngine
        from backend.services.violation_processor import ViolationProcessor
        from backend.database.models import TrafficLightState

        # Violation queue bridge Engine → Processor
        vio_queue: asyncio.Queue = asyncio.Queue(maxsize=50)

        engine    = ViolationEngine(camera_id=self._camera_id, violation_queue=vio_queue)
        processor = ViolationProcessor(queue=vio_queue)
        processor._on_saved = self._on_violation_saved   # inject callback

        # Reload zones ngay lần đầu
        self._reload_zones_if_needed(engine)

        # Khởi processor song song
        proc_task = asyncio.create_task(processor.run_loop(), name="vio_processor")

        fps_counter = 0
        fps_timer   = time.monotonic()

        while self._running:
            t0 = time.monotonic()

            # Reload zones nếu user thay đổi
            self._reload_zones_if_needed(engine)

            # Lấy frame (non-blocking với timeout nhỏ)
            if not self._running:
                break

            try:
                # Kiểm tra loop còn sống không trước khi dùng executor
                loop = asyncio.get_running_loop()
                frame = await loop.run_in_executor(
                    None, self._get_frame_blocking, 0.01
                )
            except (RuntimeError, asyncio.CancelledError):
                break

            if frame is None:
                continue

            # Map light state string → enum
            state = _parse_light_state(self._light_state)

            # Chạy ViolationEngine (state machine chính)
            from datetime import datetime, timezone
            try:
                detections = await engine.process_frame(
                    frame     = frame,
                    light_state = state,
                    timestamp = datetime.now(timezone.utc),
                )
            except Exception as exc:
                logger.error("engine error cam=%s: %s", self._camera_id, exc)
                detections = []

            # Emit bbox về UI (thread-safe qua signal)
            self.detections_ready.emit(detections)

            # FPS counter
            fps_counter += 1
            elapsed = time.monotonic() - fps_timer
            if elapsed >= 1.0:
                self.ai_fps_updated.emit(fps_counter / elapsed)
                fps_counter = 0
                fps_timer   = time.monotonic()

            # Throttle
            spent = time.monotonic() - t0
            sleep = _AI_INTERVAL - spent
            if sleep > 0:
                await asyncio.sleep(sleep)

        # Cleanup
        await processor.stop()
        proc_task.cancel()
        try:
            await proc_task
        except asyncio.CancelledError:
            pass

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_frame_blocking(self, timeout: float) -> Optional[np.ndarray]:
        try:
            return self._frame_q.get(block=True, timeout=timeout)
        except queue.Empty:
            return None

    def _reload_zones_if_needed(self, engine) -> None:
        if not self._zones_dirty:
            return
        self._zones_dirty = False
        frame_w = int(self._zones.get("frame_w") or 320)
        frame_h = int(self._zones.get("frame_h") or 240)
        zones_db_fmt = _convert_zones_to_db_format(
            self._zones, frame_w=frame_w, frame_h=frame_h
        )
        engine.load_zones(zones_db_fmt)
        logger.debug("zones reloaded cam=%s zones=%d %dx%d",
            self._camera_id, len(zones_db_fmt), frame_w, frame_h,
        )

    def _on_violation_saved(self, violation: dict) -> None:
        """Callback từ ViolationProcessor (chạy trên asyncio thread) → emit về Qt."""
        self.violation_saved.emit(violation)


# ── Utilities ──────────────────────────────────────────────────────────────────

def _parse_light_state(state_str: str):
    """Map string 'RED'/'GREEN'/'YELLOW' → TrafficLightState enum."""
    from backend.database.models import TrafficLightState
    mapping = {
        "RED":    TrafficLightState.RED,
        "GREEN":  TrafficLightState.GREEN,
        "YELLOW": TrafficLightState.YELLOW,
    }
    return mapping.get(state_str.upper(), TrafficLightState.GREEN)


def _convert_zones_to_db_format(
    zones: Dict[str, Optional[np.ndarray]],
    frame_w: int,
    frame_h: int,
) -> List[Dict[str, Any]]:
    """
    Convert zones từ StreamView (normalized 0..1 polygon)
    sang format của ViolationEngine.load_zones() (dict với x,y,width,height).
    """
    result = []

    # Stop line: ndarray shape (2,2) [[x0,y0],[x1,y1]]
    sl = zones.get("stop_line")
    if sl is not None and sl.shape == (2, 2):
        x0, y0 = int(sl[0][0] * frame_w), int(sl[0][1] * frame_h)
        x1, y1 = int(sl[1][0] * frame_w), int(sl[1][1] * frame_h)
        # Stop line: dùng bbox bao quanh đường thẳng (height nhỏ = 4px)
        result.append({
            "id":        "stop_line_0",
            "zone_name": "Stop Line",
            "zone_type": "stop_line",
            "x":         min(x0, x1),
            "y":         min(y0, y1) - 2,
            "width":     abs(x1 - x0) + 1,
            "height":    max(abs(y1 - y0) + 4, 8),
            "active":    True,
        })

    # Detect zone: ndarray shape (4,2) polygon normalized
    dz = zones.get("detect_zone")
    if dz is not None and dz.shape == (4, 2):
        pts = (dz * np.array([frame_w, frame_h])).astype(int)
        x_min, y_min = pts[:, 0].min(), pts[:, 1].min()
        x_max, y_max = pts[:, 0].max(), pts[:, 1].max()
        result.append({
            "id":        "detect_zone_0",
            "zone_name": "Detect Zone",
            "zone_type": "detection",
            "x":         int(x_min),
            "y":         int(y_min),
            "width":     int(x_max - x_min),
            "height":    int(y_max - y_min),
            "active":    True,
        })
        # Violation zone = detect zone (xe vào đây sau khi qua vạch = vi phạm)
        result.append({
            "id":        "violation_zone_0",
            "zone_name": "Violation Zone",
            "zone_type": "violation_zone",
            "x":         int(x_min),
            "y":         int(y_min),
            "width":     int(x_max - x_min),
            "height":    int(y_max - y_min),
            "active":    True,
        })

    return result
