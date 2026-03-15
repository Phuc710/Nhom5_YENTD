"""
ViolationEngine — xử lý từng frame từ stream camera.

Pipeline per-frame:
  1. Chỉ chạy detect khi đèn đỏ ổn định (>= RED_STABLE_FRAMES liên tiếp)
  2. Detect biển số trong frame
  3. Update tracker → gán track_id cho mỗi plate
  4. Kiểm tra từng track:
     a. Track có cắt qua stop_line không? (bottom_center crossing)
     b. Sau crossing, track có vào violation_zone không?
     c. Confirm thêm CONFIRM_FRAMES frame
     d. OCR vote đủ frames → chốt plate
  5. Tạo violation candidate → build evidence → lưu DB
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
from backend.services.image_service import ImageService
from backend.services.plate_tracker import PlateTracker, TrackState
from backend.services.violation_service import ViolationService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────── Hằng số thuật toán ────────────────────────────

RED_STABLE_FRAMES = 5       # số frame đỏ liên tiếp tối thiểu mới bắt đầu detect
CONFIRM_FRAMES = 4          # số frame cần xác nhận sau crossing
MIN_OCR_VOTES = 3           # số lần OCR tối thiểu để chốt biển
TRACK_EXPIRE_SECS = 8.0     # giây — expire candidate nếu không hoàn thành
MAX_BBOX_JUMP = 120         # pixel — loại track nếu bbox nhảy quá nhiều

# ────────────────────────────── Data Classes ─────────────────────────────────


@dataclass
class Zone:
    zone_id: str
    zone_name: str
    zone_type: str   # 'stop_line' | 'violation_zone' | 'detection' | 'roi'
    x: int
    y: int
    width: int
    height: int
    active: bool = True

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x2 and self.y <= py <= self.y2

    def center_y(self) -> float:
        return self.y + self.height / 2.0


@dataclass
class Candidate:
    """Vi phạm đang chờ xác nhận."""
    track_id: int
    created_at: float = field(default_factory=time.monotonic)
    confirm_count: int = 0
    best_frame: Optional[np.ndarray] = None   # frame JPEG chất lượng nhất cho OCR
    best_frame_score: float = 0.0
    crossing_ts: Optional[datetime] = None
    crossing_frame: Optional[np.ndarray] = None # frame chính xác lúc cắt vạch


# ─────────────────────────── Violation Engine ────────────────────────────────


class ViolationEngine:
    """
    Engine xử lý vi phạm cho 1 camera.

    Cách dùng (trong StreamWorker):
        engine = ViolationEngine(camera_id=1)
        await engine.load_zones()
        await engine.process_frame(frame_bgr, traffic_light_state, timestamp)
    """

    def __init__(self, camera_id: int) -> None:
        self.camera_id = camera_id
        self._tracker = PlateTracker(iou_threshold=0.30, max_miss=15, min_age_to_confirm=3)
        self._violation_service = ViolationService()
        self._image_service = ImageService()

        # Zones được load từ DB
        self._stop_lines: List[Zone] = []
        self._violation_zones: List[Zone] = []
        self._detection_zones: List[Zone] = []

        # State đèn đỏ
        self._red_frame_count: int = 0
        self._is_red_stable: bool = False

        # Candidates đang chờ confirm
        self._candidates: Dict[int, Candidate] = {}

        # Frame index toàn cục
        self._frame_idx: int = 0

        # Detector (lazy load)
        self._detector = None

    # ─────────────────────────── Zone Management ─────────────────────────────

    def load_zones(self, zones: List[Dict[str, Any]]) -> None:
        """Nạp zones (từ DB) vào engine. Gọi lại khi zones thay đổi."""
        self._stop_lines.clear()
        self._violation_zones.clear()
        self._detection_zones.clear()

        for z in zones:
            if not z.get("active", True):
                continue
            zone = Zone(
                zone_id=str(z.get("id", "")),
                zone_name=str(z.get("zone_name", "zone")),
                zone_type=str(z.get("zone_type", "detection")),
                x=int(z.get("x", 0)),
                y=int(z.get("y", 0)),
                width=int(z.get("width", 1)),
                height=int(z.get("height", 1)),
                active=bool(z.get("active", True)),
            )
            if zone.zone_type == "stop_line":
                self._stop_lines.append(zone)
            elif zone.zone_type == "violation_zone":
                self._violation_zones.append(zone)
            else:
                self._detection_zones.append(zone)

        logger.info(
            "📐 Camera %s zones nạp xong | stop_lines=%s violation_zones=%s detection=%s",
            self.camera_id,
            len(self._stop_lines),
            len(self._violation_zones),
            len(self._detection_zones),
        )

    # ─────────────────────────── Main Process Frame ───────────────────────────

    async def process_frame(
        self,
        frame: np.ndarray,
        light_state: TrafficLightState,
        timestamp: datetime,
    ) -> None:
        """Đầu vào chính: xử lý 1 frame từ stream."""
        self._frame_idx += 1

        # 1. Cập nhật state đèn đỏ
        self._update_light_state(light_state)

        # 2. Expire candidates quá lâu chưa xong
        self._expire_candidates()

        # Nếu đèn không đỏ ổn định → bỏ qua detect, reset tracker
        if not self._is_red_stable:
            if light_state != TrafficLightState.RED:
                self._tracker.reset()
                self._candidates.clear()
            return

        # 3. Detect plates trong frame
        try:
            detections = self._detect(frame)
        except Exception as exc:
            logger.warning("⚠️ Lỗi detect frame cam=%s: %s", self.camera_id, exc)
            return

        # Lọc detection trong detection_zone nếu có
        if self._detection_zones:
            detections = [d for d in detections if self._in_any_detection_zone(d)]

        # 4. Update tracker
        active_tracks = self._tracker.update(detections)

        # 5. Evaluate từng track
        for track in active_tracks:
            await self._evaluate_track(track, frame, timestamp)

    # ─────────────────────────── Track Evaluation ─────────────────────────────

    async def _evaluate_track(
        self,
        track: TrackState,
        frame: np.ndarray,
        timestamp: datetime,
    ) -> None:
        """Đánh giá 1 track: crossing, confirm, OCR vote, lưu violation."""

        # Đã tạo violation cho track này rồi → bỏ qua
        if track.violation_created:
            return

        # Kiểm tra crossing stop_line
        if not track.crossed_line:
            if self._check_crossing(track):
                track.crossed_line = True
                track.crossed_frame = self._frame_idx
                self._candidates[track.track_id] = Candidate(
                    track_id=track.track_id,
                    crossing_ts=timestamp,
                    best_frame=frame.copy(),
                    crossing_frame=frame.copy(),
                )
                logger.debug(
                    "🚦 Track %s cắt stop_line | cam=%s | frame=%s",
                    track.track_id, self.camera_id, self._frame_idx
                )
            return  # chờ frame sau để check violation_zone

        # Sau khi cắt line → kiểm tra violation_zone
        if not self._violation_zones or self._in_any_violation_zone(track):
            track.in_violation_zone = True

        candidate = self._candidates.get(track.track_id)
        if candidate is None:
            return

        # Cập nhật best frame (theo quality score)
        quality = _estimate_laplacian(frame)
        if quality > candidate.best_frame_score:
            candidate.best_frame = frame.copy()
            candidate.best_frame_score = quality

        # Confirm count
        if track.in_violation_zone or not self._violation_zones:
            candidate.confirm_count += 1

        # Đủ confirm → chốt violation
        if candidate.confirm_count >= CONFIRM_FRAMES:
            await self._commit_violation(track, candidate, timestamp)

    # ─────────────────────────── Commit Violation ─────────────────────────────

    async def _commit_violation(
        self,
        track: TrackState,
        candidate: Candidate,
        timestamp: datetime,
    ) -> None:
        """Vote OCR + build evidence + lưu vào DB."""

        if track.violation_created:
            return

        voted = track.best_plate()
        if voted and track.ocr_votes and len(track.ocr_votes) < MIN_OCR_VOTES:
            # Chưa đủ vote, chờ thêm
            return

        track.violation_created = True  # đánh dấu ngay để tránh race condition
        self._candidates.pop(track.track_id, None)

        plate_text, plate_conf = voted if voted else (None, 0.0)
        
        # Lưu ảnh bằng chứng: 
        # 1. Ảnh crop xe (từ best_frame)
        # 2. Ảnh crop biển số (từ best_frame)
        # 3. Ảnh toàn cảnh lúc cắt vạch (crossing_frame)
        vehicle_url, plate_url = await self._save_evidence(candidate.best_frame, track)
        snapshot_url = await self._image_service.save_full_image(candidate.crossing_frame, self.camera_id)

        # Lưu vi phạm
        try:
            result = await self._violation_service.create_violation(
                camera_id=self.camera_id,
                image_url=snapshot_url or "", # Sử dụng snapshot làm full_image
                plate_image_url=plate_url,
                cropped_vehicle_url=vehicle_url,
                stop_line_snapshot_url=snapshot_url,
                license_plate=plate_text,
                confidence=round(plate_conf, 4),
                traffic_light_state=TrafficLightState.RED,
                timestamp=(candidate.crossing_ts or timestamp).astimezone(timezone.utc),
                vote_count=len(track.ocr_votes),
                vote_percent=round(plate_conf * 100, 2),
                total_frames=track.age,
                track_id=track.track_id,
            )
            if isinstance(result, dict) and result.get("success") is not False:
                logger.info(
                    "🚨 Vi phạm | Cam: %s | Track: %s | Biển: %s (%.0f%%) | Votes: %s",
                    self.camera_id,
                    track.track_id,
                    plate_text or "N/A",
                    plate_conf * 100,
                    len(track.ocr_votes),
                )
            else:
                logger.debug(
                    "⚠️ Vi phạm bị bỏ qua (dedup) | Cam: %s | Track: %s | Biển: %s",
                    self.camera_id, track.track_id, plate_text or "N/A"
                )
        except Exception as exc:
            logger.error("❌ Lỗi lưu vi phạm | cam=%s track=%s: %s", self.camera_id, track.track_id, exc)

    # ─────────────────────────── Helpers ─────────────────────────────────────

    def _update_light_state(self, state: TrafficLightState) -> None:
        if state == TrafficLightState.RED:
            self._red_frame_count += 1
        else:
            self._red_frame_count = 0
        self._is_red_stable = self._red_frame_count >= RED_STABLE_FRAMES

    def _expire_candidates(self) -> None:
        now = time.monotonic()
        expired = [
            tid for tid, c in self._candidates.items()
            if now - c.created_at > TRACK_EXPIRE_SECS
        ]
        for tid in expired:
            self._candidates.pop(tid, None)
            track = self._tracker.get_track(tid)
            if track:
                track.violation_created = True  # đừng thử lại

    def _detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        if self._detector is None:
            from backend.ml.detector import get_detector
            self._detector = get_detector()
        return self._detector.process_frame(frame)

    def _check_crossing(self, track: TrackState) -> bool:
        """Kiểm tra track có cắt qua bất kỳ stop_line nào không."""
        if not self._stop_lines:
            # Không có stop_line → không bao giờ vi phạm
            return False

        curr = track.bottom_center
        prev = track.prev_bottom_center

        for line in self._stop_lines:
            line_y = line.center_y()
            # Kiểm tra hướng: xe đi từ trên xuống (prev_y < line_y <= curr_y)
            if prev is not None:
                if prev[1] < line_y <= curr[1]:
                    # Kiểm tra bottom_center có nằm trong chiều ngang của zone
                    if line.x <= curr[0] <= line.x2:
                        return True
            else:
                # Lần đầu thấy track → không thể xác định crossing
                pass

        return False

    def _in_any_violation_zone(self, track: TrackState) -> bool:
        cx, cy = track.bottom_center
        for zone in self._violation_zones:
            if zone.contains_point(cx, cy):
                return True
        return False

    def _in_any_detection_zone(self, detection: Dict[str, Any]) -> bool:
        bbox = detection.get("bbox") or {}
        cx = (int(bbox.get("x1", 0)) + int(bbox.get("x2", 0))) / 2.0
        cy = (int(bbox.get("y1", 0)) + int(bbox.get("y2", 0))) / 2.0
        for zone in self._detection_zones:
            if zone.contains_point(cx, cy):
                return True
        return False

    async def _save_evidence(
        self,
        frame: np.ndarray,
        track: TrackState,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Crop và lưu ảnh xe + biển số từ frame bằng chứng."""
        try:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = track.bbox

            # Vehicle crop — padding rộng
            pad_x = max(40, (x2 - x1) * 2)
            pad_y = max(30, (y2 - y1) * 3)
            vx1 = max(0, x1 - int(pad_x))
            vy1 = max(0, y1 - int(pad_y))
            vx2 = min(w, x2 + int(pad_x))
            vy2 = min(h, y2 + int(pad_y // 2))
            vehicle_crop = frame[vy1:vy2, vx1:vx2]

            # Plate crop — bbox trực tiếp
            plate_crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]

            vehicle_url = await self._image_service.save_vehicle_image(vehicle_crop, self.camera_id)
            plate_url = await self._image_service.save_plate_image(plate_crop, self.camera_id)
            return vehicle_url, plate_url
        except Exception as exc:
            logger.warning("⚠️ Lỗi lưu ảnh bằng chứng cam=%s: %s", self.camera_id, exc)
            return None, None


# ─────────────────────────── Utility ─────────────────────────────────────────

def _estimate_laplacian(frame: np.ndarray) -> float:
    """Ước tính độ nét của frame bằng Laplacian variance (nhanh, nhẹ)."""
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return 0.0
