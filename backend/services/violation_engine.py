"""
ViolationEngine — Phát hiện vi phạm vượt đèn đỏ (flow mới, clean).

Flow đơn giản:
  1. Detect bbox + track xe mỗi frame (PlateTracker IoU-based)
  2. Đèn đỏ ổn định (5 frame liên tiếp) → OCR chạy (cooldown 5 frame)
  3. Chốt BSX: conf>0.9 + len>5 + regex VN → plate_confirmed
  4. Xe trong violation_zone + plate_confirmed + đèn đỏ → PHẠT NGAY
  5. Enqueue ViolationEvent nhẹ → ViolationProcessor xử lý I/O nặng

Nguyên tắc:
  - KHÔNG cần voting — chốt BSX xong là phạt ngay khi vào zone
  - Tracker KHÔNG reset khi đèn xanh — giữ context was_before_line
  - _push_violation() chỉ enqueue, không block AI loop
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from backend.database.models import TrafficLightState
from backend.services.plate_tracker import PlateTracker, TrackState
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────── Constants ───────────────────────────────────

RED_STABLE_FRAMES  = 5      # frames đỏ liên tiếp để coi là ổn định
TRACK_EXPIRE_SECS  = 8.0    # hủy candidate nếu quá lâu không hoàn thành
BEFORE_LINE_MARGIN = 5      # px: bottom_center phải cao hơn vạch ít nhất N px

# ─────────────────────────────── Data Classes ────────────────────────────────


@dataclass
class Zone:
    zone_id: str
    zone_name: str
    zone_type: str   # 'stop_line' | 'violation_zone' | 'detection'
    x: int
    y: int
    width: int
    height: int
    active: bool = True

    @property
    def x2(self) -> int: return self.x + self.width

    @property
    def y2(self) -> int: return self.y + self.height

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x2 and self.y <= py <= self.y2

    def center_y(self) -> float:
        return self.y + self.height / 2.0


@dataclass
class Candidate:
    """Vi phạm đang chờ xác nhận."""
    track_id: int
    created_at: float = field(default_factory=time.monotonic)
    best_frame: Optional[np.ndarray] = None
    best_frame_score: float = 0.0
    crossing_ts: Optional[datetime] = None
    crossing_frame: Optional[np.ndarray] = None


@dataclass
class ViolationEvent:
    """Sự kiện vi phạm — data snapshot tại thời điểm xác nhận.
    Được enqueue sang ViolationProcessor để xử lý I/O nặng.
    """
    camera_id: int
    track_id: int
    track_age: int
    track_bbox: Tuple[int, int, int, int]        # vehicle bbox
    plate_bbox: Optional[Tuple[int, int, int, int]]  # plate bbox (cho crop ảnh)
    plate_text: str                               # BSX đã chốt
    plate_conf: float                             # confidence đã chốt
    best_frame: np.ndarray                        # frame chất lượng cao nhất
    crossing_frame: np.ndarray                    # frame lúc cắt vạch
    crossing_ts: Optional[datetime]
    timestamp: datetime


# ─────────────────────────────── ViolationEngine ─────────────────────────────


class ViolationEngine:
    """
    Xử lý vi phạm cho 1 camera.

    Dùng trong StreamWorker:
        engine = ViolationEngine(camera_id, violation_queue=queue)
        engine.load_zones(zones)
        await engine.process_frame(frame, light_state, timestamp)
    """

    def __init__(
        self,
        camera_id: int,
        violation_queue: Optional[asyncio.Queue] = None,
    ) -> None:
        self.camera_id        = camera_id
        self._tracker         = PlateTracker(iou_threshold=0.30, max_miss=15, min_age_to_confirm=3)
        self._violation_queue = violation_queue

        self._stop_lines:      List[Zone] = []
        self._violation_zones: List[Zone] = []
        self._detection_zones: List[Zone] = []

        self._red_frame_count: int  = 0
        self._is_red_stable:   bool = False
        self._candidates: Dict[int, Candidate] = {}
        self._frame_idx:  int = 0

        self._detector    = None
        self._detect_lock = asyncio.Lock()

    # ──────────────────────────── Zone Management ────────────────────────────

    def load_zones(self, zones: List[Dict[str, Any]]) -> None:
        """Nạp zone config từ DB. Gọi lại khi user thay đổi zone."""
        self._stop_lines.clear()
        self._violation_zones.clear()
        self._detection_zones.clear()

        for z in zones:
            if not z.get("active", True):
                continue
            zone = Zone(
                zone_id   = str(z.get("id", "")),
                zone_name = str(z.get("zone_name", "zone")),
                zone_type = str(z.get("zone_type", "detection")),
                x=int(z.get("x", 0)),   y=int(z.get("y", 0)),
                width=int(z.get("width", 1)), height=int(z.get("height", 1)),
                active=bool(z.get("active", True)),
            )
            if   zone.zone_type == "stop_line":      self._stop_lines.append(zone)
            elif zone.zone_type == "violation_zone":  self._violation_zones.append(zone)
            else:                                     self._detection_zones.append(zone)

        logger.info(
            "📐 [ENGINE] Cam %s | Vùng: stop=%d violation=%d detect=%d",
            self.camera_id, len(self._stop_lines),
            len(self._violation_zones), len(self._detection_zones),
        )

    # ───────────────────────────── Main Pipeline ─────────────────────────────

    async def process_frame(
        self,
        frame: np.ndarray,
        light_state: TrafficLightState,
        timestamp: datetime,
        config: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Entry point chính — gọi mỗi frame từ AI loop.

        Luôn detect bbox để track xe. OCR chạy theo cooldown.
        Tracker KHÔNG reset khi đèn xanh để giữ ngữ cảnh was_before_line.
        """
        self._frame_idx += 1
        self._update_light_state(light_state)
        self._expire_candidates()

        # Detect + OCR
        try:
            detections = await self._detect(frame, config=config, ocr_enabled=True)
        except Exception as exc:
            logger.error("❌ Detect lỗi | cam=%s: %s", self.camera_id, exc)
            return []

        if self._detection_zones:
            detections = [d for d in detections if self._in_any_detection_zone(d)]

        # Update tracker — truyền frame cho DeepSORT feature extraction
        active_tracks = self._tracker.update(detections, frame=frame)

        if not self._is_red_stable:
            # Đèn XANH: chỉ đánh dấu context, không xử lý vi phạm
            for track in active_tracks:
                self._mark_before_line(track)
            return detections

        # ── Đèn ĐỎ ổn định: kiểm tra vi phạm ──────────────────────────
        for track in active_tracks:
            await self._evaluate_track(track, frame, timestamp)

        return detections

    # ─────────────────────────── Track Evaluation ────────────────────────────

    async def _evaluate_track(
        self, track: TrackState, frame: np.ndarray, timestamp: datetime,
    ) -> None:
        """Đánh giá 1 track khi đèn đỏ ổn định.

        Flow mới (không cần voting):
          1. Xe cắt stop_line → tạo Candidate
          2. Xe trong violation_zone → PHẠT NGAY (nếu BSX đã chốt)
          3. Nếu không có zone → xe cắt line là đủ phạt
        """
        if track.violation_created:
            return

        # Bước 1: Kiểm tra crossing stop_line
        if not track.crossed_line:
            if self._check_crossing(track):
                track.crossed_line    = True
                track.crossed_frame   = self._frame_idx
                track.violation_phase = "CANDIDATE"
                self._candidates[track.track_id] = Candidate(
                    track_id       = track.track_id,
                    crossing_ts    = timestamp,
                    best_frame     = frame.copy(),
                    crossing_frame = frame.copy(),
                )
                logger.debug(
                    "🚦 Track %s cắt line | cam=%s | frame=%s",
                    track.track_id, self.camera_id, self._frame_idx,
                )
            return  # chờ frame tiếp theo

        # Bước 2: Kiểm tra violation_zone
        if not self._violation_zones or self._in_any_violation_zone(track):
            track.in_violation_zone = True

        candidate = self._candidates.get(track.track_id)
        if candidate is None:
            return

        # Cập nhật best frame theo độ nét
        q = _laplacian(frame)
        if q > candidate.best_frame_score:
            candidate.best_frame       = frame.copy()
            candidate.best_frame_score = q

        # ── PHẠT: xe trong zone → phạt ngay, không cần vote ──────────
        if track.in_violation_zone or not self._violation_zones:
            await self._push_violation(track, candidate, timestamp)

    # ──────────────────────────── Push to Queue ──────────────────────────────

    async def _push_violation(
        self, track: TrackState, candidate: Candidate, timestamp: datetime,
    ) -> None:
        """Đánh dấu DONE và đẩy ViolationEvent vào queue — không block AI loop."""
        if track.violation_created:
            return

        track.violation_created = True
        track.violation_phase   = "DONE"
        self._candidates.pop(track.track_id, None)

        # Lấy BSX info (nếu đã chốt thì lấy chốt, chưa thì lấy best hiện tại)
        plate_text = track.best_plate_text or "N/A"
        plate_conf = track.best_plate_conf

        event = ViolationEvent(
            camera_id      = self.camera_id,
            track_id       = track.track_id,
            track_age      = track.age,
            track_bbox     = track.bbox,
            plate_bbox     = track.plate_bbox,
            plate_text     = plate_text,
            plate_conf     = plate_conf,
            best_frame     = candidate.best_frame if candidate.best_frame is not None
                             else _blank_frame(),
            crossing_frame = candidate.crossing_frame if candidate.crossing_frame is not None
                             else _blank_frame(),
            crossing_ts    = candidate.crossing_ts,
            timestamp      = timestamp,
        )

        if self._violation_queue is not None:
            try:
                self._violation_queue.put_nowait(event)
                logger.info(
                    "🚨 [ENGINE] Vi phạm | cam=%s | track=%s | biển=%s (%.0f%%) | confirmed=%s",
                    self.camera_id, track.track_id, plate_text,
                    plate_conf * 100, track.plate_confirmed,
                )
            except asyncio.QueueFull:
                logger.warning(
                    "⚠️ [Engine] Queue đầy, drop vi phạm | cam=%s track=%s",
                    self.camera_id, track.track_id,
                )
        else:
            logger.warning(
                "⚠️ [Engine] Không có violation_queue | cam=%s — vi phạm bị mất",
                self.camera_id,
            )

    # ─────────────────────────────── Helpers ─────────────────────────────────

    def _mark_before_line(self, track: TrackState) -> None:
        """Khi đèn xanh: set was_before_line=True nếu xe đang ở phía trước stop_line."""
        if track.was_before_line or not self._stop_lines:
            return
        bx, by = track.bottom_center
        for line in self._stop_lines:
            # Xe phải nằm TRÊN vạch (y nhỏ hơn) và trong chiều ngang của vạch
            if by < (line.center_y() - BEFORE_LINE_MARGIN) and line.x <= bx <= line.x2:
                track.was_before_line = True
                return

    def _update_light_state(self, state: TrafficLightState) -> None:
        if state == TrafficLightState.RED:
            self._red_frame_count += 1
        else:
            self._red_frame_count = 0
        self._is_red_stable = self._red_frame_count >= RED_STABLE_FRAMES

    def _expire_candidates(self) -> None:
        now     = time.monotonic()
        expired = [tid for tid, c in self._candidates.items()
                   if now - c.created_at > TRACK_EXPIRE_SECS]
        for tid in expired:
            self._candidates.pop(tid, None)
            t = self._tracker.get_track(tid)
            if t:
                t.violation_created = True

    async def _detect(
        self, frame: np.ndarray, config=None, ocr_enabled: bool = True,
    ) -> List[Dict]:
        if self._detector is None:
            from backend.ml.detector import get_detector
            self._detector = get_detector()
        async with self._detect_lock:
            return await asyncio.to_thread(
                self._detector.process_frame, frame, config=config, ocr_enabled=ocr_enabled,
            )

    def _check_crossing(self, track: TrackState) -> bool:
        """Xe bị coi là cắt line khi:
          1. was_before_line=True (đã ở trước line lúc đèn xanh)
          2. bottom_center đi từ trên → xuống qua center_y của stop_line
        """
        if not self._stop_lines or not track.was_before_line:
            return False
        curr = track.bottom_center
        prev = track.prev_bottom_center
        for line in self._stop_lines:
            line_y = line.center_y()
            if prev is not None and prev[1] < line_y <= curr[1]:
                if line.x <= curr[0] <= line.x2:
                    return True
        return False

    def _in_any_violation_zone(self, track: TrackState) -> bool:
        cx, cy = track.bottom_center
        return any(z.contains_point(cx, cy) for z in self._violation_zones)

    def _in_any_detection_zone(self, detection: Dict) -> bool:
        bbox = detection.get("bbox") or {}
        cx = (int(bbox.get("x1", 0)) + int(bbox.get("x2", 0))) / 2.0
        cy = (int(bbox.get("y1", 0)) + int(bbox.get("y2", 0))) / 2.0
        return any(z.contains_point(cx, cy) for z in self._detection_zones)


# ─────────────────────────────── Utilities ───────────────────────────────────

def _laplacian(frame: np.ndarray) -> float:
    """Ước lượng độ nét frame (nhanh, dùng để chọn best_frame)."""
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return 0.0


def _blank_frame() -> np.ndarray:
    return np.zeros((1, 1, 3), dtype=np.uint8)
