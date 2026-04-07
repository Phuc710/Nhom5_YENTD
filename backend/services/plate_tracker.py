"""
Tracker biển số đơn giản dựa trên IoU — gán track_id liên tục qua nhiều frame.
Không cần DeepSORT hay SORT. Nhẹ, nhanh, đủ dùng cho bài vi phạm đèn đỏ.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Bbox dạng (x1, y1, x2, y2)
Bbox = Tuple[int, int, int, int]


@dataclass
class TrackState:
    """Trạng thái một track xe/biển số."""

    track_id: int
    bbox: Bbox
    bbox_history: Deque[Bbox] = field(default_factory=lambda: deque(maxlen=30))
    ocr_votes: List[Tuple[str, float]] = field(default_factory=list)  # (plate_text, confidence)
    miss_count: int = 0          # số frame liên tiếp không thấy track này
    age: int = 0                  # tổng số frame đã thấy track này
    crossed_line: bool = False    # đã cắt qua stop_line chưa
    crossed_frame: int = 0        # frame index lúc cắt line
    in_violation_zone: bool = False
    violation_created: bool = False  # dedup: chỉ tạo 1 violation mỗi track
    was_before_line: bool = False    # xe đã ở trước stop_line khi đèn xanh
    violation_phase: str = "MONITORING"  # MONITORING|CANDIDATE|CONFIRMED|DONE

    def update(self, bbox: Bbox) -> None:
        self.bbox = bbox
        self.bbox_history.append(bbox)
        self.miss_count = 0
        self.age += 1

    def mark_miss(self) -> None:
        self.miss_count += 1

    def vote_ocr(self, plate_text: str, confidence: float) -> None:
        if plate_text:
            self.ocr_votes.append((plate_text, confidence))

    def best_plate(self) -> Optional[Tuple[str, float]]:
        """Tính vote plate tốt nhất từ nhiều frame OCR."""
        if not self.ocr_votes:
            return None

        counts: Dict[str, List[float]] = {}
        for text, conf in self.ocr_votes:
            counts.setdefault(text, []).append(conf)

        # Ưu tiên plate nào xuất hiện nhiều nhất, sau đó confidence trung bình cao nhất
        best_text = max(counts, key=lambda t: (len(counts[t]), sum(counts[t]) / len(counts[t])))
        avg_conf = sum(counts[best_text]) / len(counts[best_text])
        return best_text, avg_conf

    @property
    def bottom_center(self) -> Tuple[float, float]:
        """Điểm giữa phía dưới bbox — dùng để kiểm tra crossing."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, float(y2))

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def prev_bottom_center(self) -> Optional[Tuple[float, float]]:
        """Điểm bottom-center frame trước, dùng để xác định hướng di chuyển."""
        if len(self.bbox_history) < 2:
            return None
        bx1, by1, bx2, by2 = self.bbox_history[-2]
        return ((bx1 + bx2) / 2.0, float(by2))


class PlateTracker:
    """
    IoU-based multi-object tracker nhẹ.

    Cách hoạt động:
    - Mỗi frame nhận danh sách bbox mới (từ detector)
    - Tính IoU giữa bbox mới và track đang sống
    - Match greedy theo IoU cao nhất (threshold 0.3)
    - Tạo track mới nếu không match
    - Expire track sau `max_miss` frame không thấy
    """

    def __init__(
        self,
        iou_threshold: float = 0.30,
        max_miss: int = 12,
        min_age_to_confirm: int = 3,
    ) -> None:
        self._iou_threshold = iou_threshold
        self._max_miss = max_miss
        self._min_age = min_age_to_confirm
        self._tracks: Dict[int, TrackState] = {}
        self._next_id = 1

    # ───────────────────────────────── Public API ─────────────────────────────

    def update(self, detections: List[Dict]) -> List[TrackState]:
        """
        Cập nhật tracker với danh sách detection mới.
        Trả về danh sách track đang sống (age >= min_age_to_confirm).
        """
        det_bboxes = [self._to_bbox(d["bbox"]) for d in detections]
        det_texts = [d.get("plate_text") or "" for d in detections]
        det_confs = [float(d.get("ocr_confidence") or d.get("confidence") or 0.0) for d in detections]

        matched_det, matched_track, unmatched_det, unmatched_track = self._match(
            det_bboxes, list(self._tracks.keys())
        )

        # Cập nhật track đã match
        for det_idx, track_id in zip(matched_det, matched_track):
            track = self._tracks[track_id]
            track.update(det_bboxes[det_idx])
            track.vote_ocr(det_texts[det_idx], det_confs[det_idx])

        # Track không thấy trong frame này
        for track_id in unmatched_track:
            self._tracks[track_id].mark_miss()

        # Tạo track mới cho detection không match
        for det_idx in unmatched_det:
            new_track = TrackState(
                track_id=self._next_id,
                bbox=det_bboxes[det_idx],
            )
            new_track.update(det_bboxes[det_idx])
            new_track.vote_ocr(det_texts[det_idx], det_confs[det_idx])
            self._tracks[self._next_id] = new_track
            self._next_id += 1

        # Xóa track đã hết thời gian
        expired = [tid for tid, t in self._tracks.items() if t.miss_count > self._max_miss]
        for tid in expired:
            self._tracks.pop(tid, None)

        # Trả về track đủ tuổi
        return [t for t in self._tracks.values() if t.age >= self._min_age]

    def get_track(self, track_id: int) -> Optional[TrackState]:
        return self._tracks.get(track_id)

    def get_active_tracks(self) -> List[TrackState]:
        return list(self._tracks.values())

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    # ───────────────────────────────── Internal ───────────────────────────────

    def _match(
        self,
        det_bboxes: List[Bbox],
        track_ids: List[int],
    ) -> Tuple[List[int], List[int], List[int], List[int]]:
        """Greedy IoU matching. Trả về (matched_det_idx, matched_track_id, unmatched_det_idx, unmatched_track_id)."""
        if not det_bboxes or not track_ids:
            return [], [], list(range(len(det_bboxes))), list(track_ids)

        track_bboxes = [self._tracks[tid].bbox for tid in track_ids]
        iou_matrix = self._compute_iou_matrix(det_bboxes, track_bboxes)

        matched_det: List[int] = []
        matched_track: List[int] = []
        used_det = set()
        used_track = set()

        # Sort theo IoU cao nhất -> match greedy
        order = np.dstack(np.unravel_index(np.argsort(-iou_matrix, axis=None), iou_matrix.shape))[0]
        for di, ti in order:
            if di in used_det or ti in used_track:
                continue
            if iou_matrix[di, ti] < self._iou_threshold:
                break
            matched_det.append(int(di))
            matched_track.append(track_ids[int(ti)])
            used_det.add(di)
            used_track.add(ti)

        unmatched_det = [i for i in range(len(det_bboxes)) if i not in used_det]
        unmatched_track = [track_ids[i] for i in range(len(track_ids)) if i not in used_track]
        return matched_det, matched_track, unmatched_det, unmatched_track

    @staticmethod
    def _compute_iou_matrix(
        boxes_a: List[Bbox], boxes_b: List[Bbox]
    ) -> np.ndarray:
        matrix = np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)
        for i, a in enumerate(boxes_a):
            for j, b in enumerate(boxes_b):
                matrix[i, j] = _iou(a, b)
        return matrix

    @staticmethod
    def _to_bbox(d: dict) -> Bbox:
        return (int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"]))


# ────────────────────────────── Utility ───────────────────────────────────────

def _iou(a: Bbox, b: Bbox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / (area_a + area_b - inter)
