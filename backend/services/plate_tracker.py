"""
PlateTracker — Tracking xe + chốt BSX.

Hỗ trợ 2 thuật toán:
  1. DeepSORT (mặc định) — appearance feature + IoU, chống mất dấu/nhảy ID
  2. IoU Tracker (fallback) — nhanh nhẹ, chỉ dùng IoU thuần

Chốt BSX (3 điều kiện đồng thời):
  1. ocr_conf > 0.9
  2. len(plate) > 5
  3. check_legit_plate(plate) — regex format BSX VN

Cooldown: OCR thất bại → đợi 5 frame. Chốt xong → ngừng OCR.
"""
from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import torch

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────
OCR_SUCCESS_CONF = 0.9
MIN_PLATE_LEN = 5
OCR_INTERVAL = 5

# Regex BSX VN
_RE_FULL = re.compile(r'^[0-9]{2}[A-Za-z][0-9A-Za-z]?[-.]?[0-9]{4,5}$')
_RE_MOTO = re.compile(r'^[A-Za-z]{2}[0-9]{4,5}$')
_RE_CAR  = re.compile(r'[A-Za-z][0-9]{4,}')

Bbox = Tuple[int, int, int, int]


def check_legit_plate(plate: str) -> bool:
    """Kiểm tra format BSX Việt Nam: 51A-12345, AB1234, ..."""
    if not plate or len(plate) < MIN_PLATE_LEN:
        return False
    c = plate.replace("-", "").replace(".", "").replace(" ", "").upper()
    return bool(_RE_FULL.match(c) or _RE_MOTO.match(c) or _RE_CAR.search(c))


# ─── TrackState ─────────────────────────────────────────────────────────────

@dataclass
class TrackState:
    """Trạng thái 1 track xe."""
    track_id: int
    bbox: Bbox
    bbox_history: Deque[Bbox] = field(default_factory=lambda: deque(maxlen=30))

    # OCR
    plate_confirmed: bool = False
    best_plate_text: str = ""
    best_plate_conf: float = 0.0
    ocr_frame_counter: int = 0
    ocr_last_attempt_frame: int = 0
    plate_bbox: Optional[Bbox] = None

    # Tracking
    miss_count: int = 0
    age: int = 0
    crossed_line: bool = False
    crossed_frame: int = 0
    in_violation_zone: bool = False
    violation_created: bool = False
    was_before_line: bool = False
    violation_phase: str = "MONITORING"

    def update(self, bbox: Bbox) -> None:
        self.bbox = bbox
        self.bbox_history.append(bbox)
        self.miss_count = 0
        self.age += 1
        self.ocr_frame_counter += 1

    def mark_miss(self) -> None:
        self.miss_count += 1

    def should_ocr(self) -> bool:
        if self.plate_confirmed:
            return False
        return (self.ocr_frame_counter - self.ocr_last_attempt_frame) >= OCR_INTERVAL

    def try_confirm_plate(self, text: str, conf: float) -> bool:
        """Thử chốt BSX. Chỉ override khi tốt hơn. Trả True nếu chốt."""
        self.ocr_last_attempt_frame = self.ocr_frame_counter
        if not text or text == "unknown":
            return False

        if conf > self.best_plate_conf:
            self.best_plate_text = text
            self.best_plate_conf = conf

        if conf > OCR_SUCCESS_CONF and len(text) > MIN_PLATE_LEN and check_legit_plate(text):
            self.plate_confirmed = True
            self.best_plate_text = text
            self.best_plate_conf = conf
            logger.info("✅ [CHỐT] Track %s | %s | conf=%.2f", self.track_id, text, conf)
            return True
        return False

    @property
    def bottom_center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, float(y2))

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def prev_bottom_center(self) -> Optional[Tuple[float, float]]:
        if len(self.bbox_history) < 2:
            return None
        bx1, by1, bx2, by2 = self.bbox_history[-2]
        return ((bx1 + bx2) / 2.0, float(by2))


# ─── PlateTracker ───────────────────────────────────────────────────────────

class PlateTracker:
    """
    Tracker hỗ trợ 2 mode:
      - "deepsort": DeepSORT (appearance + IoU), chống nhảy ID
      - "iou":      IoU greedy matching, nhẹ và nhanh

    DeepSORT là mặc định. Fallback sang IoU nếu thiếu model.
    """

    def __init__(
        self,
        mode: str = "deepsort",
        model_path: str = "models/deepsort/ckpt.t7",
        iou_threshold: float = 0.30,
        max_miss: int = 15,
        min_age_to_confirm: int = 3,
    ) -> None:
        self._mode = mode
        self._iou_threshold = iou_threshold
        self._max_miss = max_miss
        self._min_age = min_age_to_confirm
        self._tracks: Dict[int, TrackState] = {}
        self._next_id = 1

        # DeepSORT engine
        self._deepsort = None
        if mode == "deepsort":
            self._deepsort = self._init_deepsort(model_path)
            if self._deepsort is None:
                logger.warning("⚠️ DeepSORT init thất bại → fallback IoU tracker")
                self._mode = "iou"

    def _init_deepsort(self, model_path: str):
        """Init DeepSORT. Trả None nếu không có model."""
        # Resolve path tương đối từ backend/
        if not os.path.isabs(model_path):
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base, model_path)

        if not os.path.exists(model_path):
            logger.warning("⚠️ DeepSORT model không tìm thấy: %s", model_path)
            return None

        try:
            from backend.tracking.deep_sort import DeepSort
            use_cuda = torch.cuda.is_available()
            ds = DeepSort(
                model_path,
                max_dist=0.2,
                min_confidence=0.3,
                nms_max_overlap=0.5,
                max_iou_distance=0.7,
                max_age=70,
                n_init=3,
                nn_budget=100,
                use_cuda=use_cuda,
            )
            logger.info("✅ DeepSORT loaded | model=%s | cuda=%s", model_path, use_cuda)
            return ds
        except Exception as exc:
            logger.error("❌ DeepSORT load error: %s", exc)
            return None

    @property
    def mode(self) -> str:
        return self._mode

    # ───────────────────────────── Public API ─────────────────────────────

    def update(self, detections: List[Dict], frame: Optional[np.ndarray] = None) -> List[TrackState]:
        """
        Cập nhật tracker. Trả về tracks đang sống (age >= min_age).

        Args:
            detections: [{bbox: {x1,y1,x2,y2}, plate_text, confidence, ...}]
            frame: ảnh gốc BGR (cần cho DeepSORT feature extraction)
        """
        if self._mode == "deepsort" and self._deepsort is not None and frame is not None:
            return self._update_deepsort(detections, frame)
        return self._update_iou(detections)

    def get_track(self, track_id: int) -> Optional[TrackState]:
        return self._tracks.get(track_id)

    def get_active_tracks(self) -> List[TrackState]:
        return list(self._tracks.values())

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    # ───────────────────────── DeepSORT Update ────────────────────────────

    def _update_deepsort(self, detections: List[Dict], frame: np.ndarray) -> List[TrackState]:
        """Update bằng DeepSORT: appearance features + IoU."""
        if not detections:
            # Vẫn predict để cập nhật miss count
            for t in self._tracks.values():
                t.mark_miss()
            self._expire()
            return [t for t in self._tracks.values() if t.age >= self._min_age]

        # Convert detections → format DeepSORT (bbox_xywh, confidences)
        bbox_xywh = []
        confs = []
        det_texts = []
        det_ocr_confs = []
        for d in detections:
            b = d["bbox"]
            x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            w = x2 - x1
            h = y2 - y1
            bbox_xywh.append([cx, cy, w, h])
            confs.append(float(d.get("confidence") or d.get("detection_confidence") or 0.5))
            det_texts.append(d.get("plate_text") or "")
            det_ocr_confs.append(float(d.get("ocr_confidence") or d.get("confidence") or 0.0))

        bbox_xywh = np.array(bbox_xywh, dtype=np.float32)
        confs_arr = np.array(confs, dtype=np.float32)

        # DeepSORT update → [[x1,y1,x2,y2,track_id], ...]
        outputs = self._deepsort.update(bbox_xywh, confs_arr, frame)

        # Map DeepSORT outputs → TrackState
        seen_ids = set()
        if len(outputs) > 0:
            for out in outputs:
                x1, y1, x2, y2, tid = int(out[0]), int(out[1]), int(out[2]), int(out[3]), int(out[4])
                bbox = (x1, y1, x2, y2)
                seen_ids.add(tid)

                if tid not in self._tracks:
                    self._tracks[tid] = TrackState(track_id=tid, bbox=bbox)
                    self._next_id = max(self._next_id, tid + 1)

                track = self._tracks[tid]
                track.update(bbox)

                # Match OCR text từ detection gần nhất (by IoU)
                best_det_idx = self._match_nearest_det(bbox, detections)
                if best_det_idx is not None:
                    text = det_texts[best_det_idx]
                    conf = det_ocr_confs[best_det_idx]
                    if text and not track.plate_confirmed:
                        track.try_confirm_plate(text, conf)

        # Mark miss cho tracks không xuất hiện
        for tid, t in self._tracks.items():
            if tid not in seen_ids:
                t.mark_miss()

        self._expire()
        return [t for t in self._tracks.values() if t.age >= self._min_age]

    def _match_nearest_det(self, bbox: Bbox, detections: List[Dict]) -> Optional[int]:
        """Tìm detection gần nhất bằng IoU."""
        best_idx, best_iou = None, 0.0
        for i, d in enumerate(detections):
            b = d["bbox"]
            det_bbox = (int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"]))
            iou = _iou(bbox, det_bbox)
            if iou > best_iou:
                best_iou = iou
                best_idx = i
        return best_idx if best_iou > 0.3 else None

    # ─────────────────────────── IoU Update ───────────────────────────────

    def _update_iou(self, detections: List[Dict]) -> List[TrackState]:
        """Update bằng IoU greedy matching (fallback nhẹ)."""
        det_bboxes = [self._to_bbox(d["bbox"]) for d in detections]
        det_texts = [d.get("plate_text") or "" for d in detections]
        det_confs = [float(d.get("ocr_confidence") or d.get("confidence") or 0.0) for d in detections]

        matched_det, matched_track, unmatched_det, unmatched_track = self._greedy_match(
            det_bboxes, list(self._tracks.keys())
        )

        for det_idx, track_id in zip(matched_det, matched_track):
            track = self._tracks[track_id]
            track.update(det_bboxes[det_idx])
            if det_texts[det_idx] and not track.plate_confirmed:
                track.try_confirm_plate(det_texts[det_idx], det_confs[det_idx])

        for track_id in unmatched_track:
            self._tracks[track_id].mark_miss()

        for det_idx in unmatched_det:
            t = TrackState(track_id=self._next_id, bbox=det_bboxes[det_idx])
            t.update(det_bboxes[det_idx])
            if det_texts[det_idx]:
                t.try_confirm_plate(det_texts[det_idx], det_confs[det_idx])
            self._tracks[self._next_id] = t
            self._next_id += 1

        self._expire()
        return [t for t in self._tracks.values() if t.age >= self._min_age]

    def _expire(self) -> None:
        expired = [tid for tid, t in self._tracks.items() if t.miss_count > self._max_miss]
        for tid in expired:
            self._tracks.pop(tid, None)

    def _greedy_match(self, det_bboxes, track_ids):
        if not det_bboxes or not track_ids:
            return [], [], list(range(len(det_bboxes))), list(track_ids)

        track_bboxes = [self._tracks[tid].bbox for tid in track_ids]
        n_det, n_trk = len(det_bboxes), len(track_bboxes)
        iou_matrix = np.zeros((n_det, n_trk), dtype=np.float32)
        for i in range(n_det):
            for j in range(n_trk):
                iou_matrix[i, j] = _iou(det_bboxes[i], track_bboxes[j])

        matched_det, matched_track = [], []
        used_det, used_track = set(), set()
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

        unmatched_det = [i for i in range(n_det) if i not in used_det]
        unmatched_track = [track_ids[i] for i in range(n_trk) if i not in used_track]
        return matched_det, matched_track, unmatched_det, unmatched_track

    @staticmethod
    def _to_bbox(d: dict) -> Bbox:
        return (int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"]))


# ─── Utility ────────────────────────────────────────────────────────────────

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
