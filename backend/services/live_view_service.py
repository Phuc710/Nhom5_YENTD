"""Luu trang thai live-view moi nhat de web admin ve boxing overlay."""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional


def _score_of(detection: Dict[str, Any]) -> float:
    return float(
        detection.get("overall_confidence")
        or detection.get("ocr_confidence")
        or detection.get("confidence")
        or 0.0
    )


def _sanitize_detection(detection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plate_text": detection.get("plate_text"),
        "confidence": round(_score_of(detection), 4),
        "bbox": detection.get("bbox"),
        "vehicle_crop_bbox": detection.get("vehicle_crop_bbox"),
        "matched_zones": detection.get("matched_zones") or [],
        "matched_stop_lines": detection.get("matched_stop_lines") or [],
        "crossed_stop_line": bool(detection.get("crossed_stop_line")),
        "is_violation": bool(detection.get("is_violation")),
    }


def _best_detection(detections: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not detections:
        return None
    return max((_sanitize_detection(item) for item in detections), key=lambda item: item["confidence"])


class LiveViewStore:
    """Bo nho tam cho overlay stream va detect preview cua tung camera."""

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
        sanitized_detections = [_sanitize_detection(item) for item in detections or []]
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
                    "detection_count": len(sanitized_detections),
                    "latest_detection": _best_detection(detections or []),
                    "detections": sanitized_detections,
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
