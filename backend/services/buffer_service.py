"""Quản lý buffer frame theo phiên đèn đỏ của từng camera."""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple
import threading

from utils.logger import get_logger

logger = get_logger(__name__)


class FrameBuffer:
    def __init__(
        self,
        window_seconds: int = 120,
        min_frames: int = 3,
        timeout_seconds: int = 3,
        high_confidence_threshold: float = 0.75,
    ):
        self.window_seconds = window_seconds
        self.min_frames = min_frames
        self.timeout_seconds = timeout_seconds
        self.high_confidence_threshold = high_confidence_threshold
        self._buffer: Dict[int, List[Dict]] = defaultdict(list)
        self._trackers: Dict[int, object] = {}
        self._last_frame_at: Dict[int, datetime] = {}
        self._lock = threading.Lock()

    def add_frame(self, camera_id: int, frame_data: Dict, emergency: bool = False) -> None:
        with self._lock:
            frame_data["received_at"] = datetime.now()
            frame_data["emergency"] = emergency
            self._buffer[camera_id].append(frame_data)
            self._last_frame_at[camera_id] = datetime.now()
            self._cleanup(camera_id)

    def get_frames(self, camera_id: int) -> List[Dict]:
        with self._lock:
            self._cleanup(camera_id)
            return list(self._buffer[camera_id])

    def consume_frames(self, camera_id: int) -> List[Dict]:
        """Lấy và xóa toàn bộ frame của một phiên đèn đỏ."""
        with self._lock:
            frames = list(self._buffer[camera_id])
            self._buffer[camera_id].clear()
            self._trackers.pop(camera_id, None)
            self._last_frame_at.pop(camera_id, None)
            return frames

    def should_process(self, camera_id: int) -> Tuple[bool, str]:
        """
        Chỉ chốt sớm khi:
        - có cờ emergency
        - có OCR đủ mạnh
        - hoặc buffer bị bỏ quên quá lâu
        """
        frames = self.get_frames(camera_id)
        if not frames:
            return False, "no_frames"

        if any(frame.get("emergency") for frame in frames):
            return True, f"emergency ({len(frames)} frames)"

        strong_result = self._find_high_confidence_result(frames)
        if strong_result:
            return True, (
                f"high_confidence plate={strong_result['license_plate']} "
                f"confidence={strong_result['confidence']:.2f}"
            )

        last = self._last_frame_at.get(camera_id)
        if last:
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed >= self.timeout_seconds:
                return True, f"stale_red_buffer ({elapsed:.1f}s, {len(frames)} frames)"

        return False, f"wait_red_phase_end ({len(frames)} frames)"

    def get_tracker(self, camera_id: int):
        if camera_id not in self._trackers:
            from services.tracking_service import SORTTracker

            self._trackers[camera_id] = SORTTracker()
        return self._trackers[camera_id]

    def _find_high_confidence_result(self, frames: List[Dict]) -> Dict | None:
        best_candidate = None
        for frame in frames:
            for detection in frame.get("detections", []):
                plate_text = detection.get("plate_text")
                confidence = self._extract_plate_confidence(detection)
                if not plate_text or confidence < self.high_confidence_threshold:
                    continue
                if best_candidate is None or confidence > best_candidate["confidence"]:
                    best_candidate = {
                        "license_plate": plate_text,
                        "confidence": confidence,
                    }
        return best_candidate

    @staticmethod
    def _extract_plate_confidence(detection: Dict) -> float:
        return float(
            detection.get("overall_confidence")
            or detection.get("ocr_confidence")
            or detection.get("confidence")
            or 0.0
        )

    def _cleanup(self, camera_id: int) -> None:
        last = self._last_frame_at.get(camera_id)
        if not last:
            return

        elapsed = (datetime.now() - last).total_seconds()
        if elapsed < self.window_seconds:
            return

        if self._buffer[camera_id]:
            logger.warning(
                "Xóa buffer đỏ cũ camera=%s vì quá hạn %ss",
                camera_id,
                self.window_seconds,
            )
        self._buffer[camera_id].clear()
        self._trackers.pop(camera_id, None)
        self._last_frame_at.pop(camera_id, None)


def _make_buffer() -> FrameBuffer:
    from config.settings import get_settings

    settings = get_settings()
    return FrameBuffer(
        window_seconds=settings.buffer_window_seconds,
        min_frames=settings.buffer_min_frames,
        timeout_seconds=settings.buffer_timeout_seconds,
        high_confidence_threshold=settings.vote_confidence_threshold,
    )


frame_buffer = _make_buffer()
