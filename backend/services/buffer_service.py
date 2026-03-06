"""
services/buffer_service.py — Frame Buffer Manager
Quản lý buffer multi-frame từ ESP32 để voting OCR.

Modes:
  Normal    — Buffer cho đến khi đủ min_frames
  Timeout   — Xử lý nếu không có frame mới sau timeout_seconds
  Emergency — Xử lý ngay lập tức (ESP32 báo mode khẩn cấp)
"""
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import threading

from utils.logger import get_logger

logger = get_logger(__name__)


class FrameBuffer:
    def __init__(self, window_seconds: int = 10, min_frames: int = 3, timeout_seconds: int = 3):
        self.window_seconds  = window_seconds
        self.min_frames      = min_frames
        self.timeout_seconds = timeout_seconds
        self._buffer:        Dict[int, List[Dict]] = defaultdict(list)
        self._trackers:      Dict[int, object]     = {}
        self._last_frame_at: Dict[int, datetime]   = {}
        self._lock = threading.Lock()

    # ---- Add / get / consume --------------------------------

    def add_frame(self, camera_id: int, frame_data: Dict, emergency: bool = False) -> None:
        with self._lock:
            frame_data["received_at"] = datetime.now()
            frame_data["emergency"]   = emergency
            self._buffer[camera_id].append(frame_data)
            self._last_frame_at[camera_id] = datetime.now()
            self._cleanup(camera_id)

    def get_frames(self, camera_id: int) -> List[Dict]:
        with self._lock:
            self._cleanup(camera_id)
            return list(self._buffer[camera_id])

    def consume_frames(self, camera_id: int) -> List[Dict]:
        """Lấy và xóa tất cả frames của camera"""
        with self._lock:
            frames = list(self._buffer[camera_id])
            self._buffer[camera_id].clear()
            # Reset tracker sau mỗi lần finalize
            self._trackers.pop(camera_id, None)
            return frames

    # ---- Decision logic -------------------------------------

    def should_process(self, camera_id: int) -> Tuple[bool, str]:
        """
        Quyết định có nên process không.
        Returns: (should_process: bool, reason: str)
        """
        frames = self.get_frames(camera_id)
        if not frames:
            return False, "no_frames"

        if any(f.get("emergency") for f in frames):
            return True, f"emergency ({len(frames)} frames)"

        if len(frames) >= self.min_frames:
            return True, f"sufficient_frames ({len(frames)}/{self.min_frames})"

        last = self._last_frame_at.get(camera_id)
        if last:
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed >= self.timeout_seconds:
                return True, f"timeout ({elapsed:.1f}s, {len(frames)} frames)"

        return False, f"buffering ({len(frames)}/{self.min_frames})"

    # ---- Tracker per camera ---------------------------------

    def get_tracker(self, camera_id: int):
        if camera_id not in self._trackers:
            from services.tracking_service import SORTTracker
            self._trackers[camera_id] = SORTTracker()
        return self._trackers[camera_id]

    # ---- Cleanup old frames ---------------------------------

    def _cleanup(self, camera_id: int) -> None:
        cutoff = datetime.now() - timedelta(seconds=self.window_seconds)
        self._buffer[camera_id] = [
            f for f in self._buffer[camera_id]
            if f["received_at"] > cutoff
        ]


# ---- Singleton -----------------------------------------------
def _make_buffer() -> FrameBuffer:
    from config.settings import get_settings
    s = get_settings()
    return FrameBuffer(
        window_seconds  = s.buffer_window_seconds,
        min_frames      = s.buffer_min_frames,
        timeout_seconds = s.buffer_timeout_seconds,
    )

frame_buffer = _make_buffer()
