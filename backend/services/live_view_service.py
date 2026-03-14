"""Lưu trạng thái live-view mới nhất cho từng camera để web vẽ overlay."""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional


def _best_detection(detections: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_score = -1.0

    for detection in detections or []:
        score = float(
            detection.get("overall_confidence")
            or detection.get("ocr_confidence")
            or detection.get("confidence")
            or 0.0
        )
        if score <= best_score:
            continue
        best_score = score
        best = {
            "plate_text": detection.get("plate_text"),
            "confidence": round(score, 4),
            "bbox": detection.get("bbox"),
        }

    return best


class LiveViewStore:
    """Bộ nhớ tạm cho overlay stream và trạng thái nhận diện gần nhất."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: Dict[int, Dict[str, Any]] = {}

    def update_frame(
        self,
        camera_id: int,
        *,
        timestamp: datetime,
        frame_width: int,
        frame_height: int,
        traffic_light_state: str,
        operation_mode: str,
        tl_state_ms: int,
        quality_score: float,
        processing_ms: int,
        detections: list[Dict[str, Any]],
    ) -> None:
        with self._lock:
            state = self._states.setdefault(camera_id, {})
            state.update(
                {
                    "camera_id": camera_id,
                    "captured_at": timestamp.isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "frame_width": frame_width,
                    "frame_height": frame_height,
                    "traffic_light_state": traffic_light_state,
                    "operation_mode": operation_mode,
                    "tl_state_ms": tl_state_ms,
                    "quality_score": round(float(quality_score or 0.0), 2),
                    "processing_ms": processing_ms,
                    "detection_count": len(detections or []),
                    "latest_detection": _best_detection(detections or []),
                }
            )

    def attach_violation(self, camera_id: int, violation: Dict[str, Any]) -> None:
        with self._lock:
            state = self._states.setdefault(camera_id, {})
            state["last_violation"] = {
                "id": violation.get("id"),
                "license_plate": violation.get("license_plate"),
                "timestamp": violation.get("timestamp"),
                "full_image_url": violation.get("full_image_url"),
                "cropped_plate_url": violation.get("cropped_plate_url"),
            }

    def get_state(self, camera_id: int) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._states.get(camera_id, {}))


live_view_store = LiveViewStore()
