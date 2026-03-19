"""Luu trang thai live-view moi nhat de web admin ve boxing overlay."""

from __future__ import annotations

import asyncio
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional, List


def _score_of(detection: Dict[str, Any]) -> float:
    return float(
        detection.get("overall_confidence")
        or detection.get("ocr_confidence")
        or detection.get("confidence")
        or 0.0
    )


def _sanitize_detection(detection: Dict[str, Any]) -> Dict[str, Any]:
    bbox = detection.get("bbox")
    if isinstance(bbox, dict):
        bbox = [bbox.get("x1", 0), bbox.get("y1", 0), bbox.get("x2", 0), bbox.get("y2", 0)]
        
    vehicle_bbox = detection.get("vehicle_crop_bbox")
    if isinstance(vehicle_bbox, dict):
        vehicle_bbox = [vehicle_bbox.get("x1", 0), vehicle_bbox.get("y1", 0), vehicle_bbox.get("x2", 0), vehicle_bbox.get("y2", 0)]

    return {
        "plate_text": detection.get("plate_text"),
        "confidence": round(_score_of(detection), 4),
        "bbox": bbox,
        "vehicle_crop_bbox": vehicle_bbox,
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
        self._frame_bytes: Dict[int, bytes] = {}
        
        # Pub/Sub queues cho tung client
        self._stream_subs: Dict[int, List[asyncio.Queue[bytes]]] = {}
        self._sse_subs: Dict[int, List[asyncio.Queue[Dict[str, Any]]]] = {}

    def subscribe_stream(self, camera_id: int) -> asyncio.Queue[bytes]:
        q = asyncio.Queue(maxsize=3)
        with self._lock:
            self._stream_subs.setdefault(camera_id, []).append(q)
            latest = self._frame_bytes.get(camera_id)
            if latest:
                q.put_nowait(latest)
        return q

    def unsubscribe_stream(self, camera_id: int, q: asyncio.Queue[bytes]) -> None:
        with self._lock:
            subs = self._stream_subs.get(camera_id)
            if subs and q in subs:
                subs.remove(q)

    def subscribe_sse(self, camera_id: int) -> asyncio.Queue[Dict[str, Any]]:
        q = asyncio.Queue(maxsize=5)
        with self._lock:
            self._sse_subs.setdefault(camera_id, []).append(q)
            latest = self._states.get(camera_id)
            if latest:
                q.put_nowait(deepcopy(latest))
        return q

    def unsubscribe_sse(self, camera_id: int, q: asyncio.Queue[Dict[str, Any]]) -> None:
        with self._lock:
            subs = self._sse_subs.get(camera_id)
            if subs and q in subs:
                subs.remove(q)

    def update_jpeg(self, camera_id: int, jpeg_bytes: bytes) -> None:
        with self._lock:
            self._frame_bytes[camera_id] = jpeg_bytes
            
            subs = self._stream_subs.get(camera_id, [])
            for q in subs:
                if q.full():
                    try: q.get_nowait()
                    except asyncio.QueueEmpty: pass
                try: q.put_nowait(jpeg_bytes)
                except asyncio.QueueFull: pass

    def update_runtime(
        self,
        camera_id: int,
        *,
        traffic_light_state: Optional[str] = None,
        operation_mode: Optional[str] = None,
        tl_state_ms: Optional[int] = None,
    ) -> None:
        with self._lock:
            state = self._states.setdefault(camera_id, {})
            changed = False
            if traffic_light_state not in (None, ""):
                normalized = str(traffic_light_state).strip().lower()
                if state.get("traffic_light_state") != normalized:
                    state["traffic_light_state"] = normalized
                    changed = True
            if operation_mode not in (None, ""):
                if state.get("operation_mode") != operation_mode:
                    state["operation_mode"] = operation_mode
                    changed = True
            if tl_state_ms is not None:
                normalized_ms = int(tl_state_ms)
                if state.get("tl_state_ms") != normalized_ms:
                    state["tl_state_ms"] = normalized_ms
                    changed = True
            state["updated_at"] = datetime.now().isoformat()

            if not changed:
                return

            state_data = deepcopy(state)
            for q in self._sse_subs.get(camera_id, []):
                if q.full():
                    try: q.get_nowait()
                    except asyncio.QueueEmpty: pass
                try: q.put_nowait(state_data)
                except asyncio.QueueFull: pass

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
        jpeg_bytes: Optional[bytes] = None,
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
            if jpeg_bytes is not None:
                self._frame_bytes[camera_id] = jpeg_bytes
                
            state_data = deepcopy(state)
            
            # Notify stream if jpeg_bytes was provided
            if jpeg_bytes is not None:
                for q in self._stream_subs.get(camera_id, []):
                    if q.full():
                        try: q.get_nowait()
                        except asyncio.QueueEmpty: pass
                    try: q.put_nowait(jpeg_bytes)
                    except asyncio.QueueFull: pass
            
            # Notify SSE
            for q in self._sse_subs.get(camera_id, []):
                if q.full():
                    try: q.get_nowait()
                    except asyncio.QueueEmpty: pass
                try: q.put_nowait(state_data)
                except asyncio.QueueFull: pass

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
            state_data = deepcopy(state)
            
            for q in self._sse_subs.get(camera_id, []):
                if q.full():
                    try: q.get_nowait()
                    except asyncio.QueueEmpty: pass
                try: q.put_nowait(state_data)
                except asyncio.QueueFull: pass

    def get_state(self, camera_id: int) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._states.get(camera_id, {}))

    def get_latest_frame(self, camera_id: int) -> Optional[bytes]:
        with self._lock:
            return self._frame_bytes.get(camera_id)


live_view_store = LiveViewStore()
