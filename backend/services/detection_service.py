"""Admin detection flow: preview boxing va upload anh detect/save all."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional
from zoneinfo import ZoneInfo

import cv2
import numpy as np

from backend.database.models import TrafficLightState
from backend.repositories.camera_repository import CameraRepository
from backend.services.image_service import ImageService
from backend.services.live_view_service import live_view_store
from backend.services.violation_service import ViolationService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.ml.detector import LicensePlateDetector


class DetectionService:
    def __init__(self) -> None:
        from backend.config.settings import get_settings

        self._settings = get_settings()
        self._camera_repository = CameraRepository()
        self._image_service = ImageService()
        self._violation_service = ViolationService()
        self._detector: Optional["LicensePlateDetector"] = None

    async def preview_frame(
        self,
        *,
        camera_id: int,
        image_bytes: bytes,
        captured_at: Optional[str] = None,
        traffic_light_state: str = TrafficLightState.RED.value,
    ) -> Dict[str, Any]:
        frame = self._decode_image(image_bytes)
        captured_dt = self._parse_timestamp(captured_at)
        tl_state = self._parse_traffic_light_state(traffic_light_state)
        if tl_state != TrafficLightState.RED:
            live_view_store.update_frame(
                camera_id,
                timestamp=captured_dt.astimezone(ZoneInfo(self._settings.timezone)),
                frame_width=int(frame.shape[1]),
                frame_height=int(frame.shape[0]),
                traffic_light_state=tl_state.value,
                operation_mode="idle",
                tl_state_ms=0,
                quality_score=self._estimate_quality_score(frame),
                processing_ms=0,
                detections=[],
            )
            self._camera_repository.touch_last_seen(camera_id)
            return {
                "success": True,
                "camera_id": camera_id,
                "captured_at": captured_dt.isoformat(),
                "processing_ms": 0,
                "quality_score": self._estimate_quality_score(frame),
                "detection_count": 0,
                "detections": [],
                "skipped_reason": "light_not_red",
                "traffic_light_state": tl_state.value,
            }

        analyzed = self._analyze_frame(
            camera_id=camera_id,
            image_bytes=image_bytes,
            captured_at=captured_at,
            location=None,
            traffic_light_state=traffic_light_state,
            operation_mode="preview",
        )
        return {
            "success": True,
            "camera_id": camera_id,
            "captured_at": analyzed["captured_at"].isoformat(),
            "processing_ms": analyzed["processing_ms"],
            "quality_score": analyzed["quality_score"],
            "detection_count": len(analyzed["detections"]),
            "detections": analyzed["detections"],
            "traffic_light_state": analyzed["traffic_light_state"].value,
        }

    async def process_upload_image(
        self,
        *,
        camera_id: int,
        image_bytes: bytes,
        captured_at: Optional[str] = None,
        location: Optional[str] = None,
        traffic_light_state: str = TrafficLightState.RED.value,
    ) -> Dict[str, Any]:
        analyzed = self._analyze_frame(
            camera_id=camera_id,
            image_bytes=image_bytes,
            captured_at=captured_at,
            location=location,
            traffic_light_state=traffic_light_state,
            operation_mode="upload",
        )
        camera = analyzed["camera"]
        event_location = analyzed["location"]
        tl_state = analyzed["traffic_light_state"]
        captured_dt = analyzed["captured_at"]
        processing_ms = analyzed["processing_ms"]
        quality_score = analyzed["quality_score"]
        frame = analyzed["frame"]
        detections = analyzed["detections"]

        items = []
        for detection in detections:
            item = await self._persist_detection(
                camera_id=camera_id,
                frame=frame,
                detection=detection,
                captured_dt=captured_dt,
                traffic_light_state=tl_state,
                quality_score=quality_score,
                processing_ms=processing_ms,
            )
            items.append(item)
            if item.get("violation_saved") and item.get("violation"):
                live_view_store.attach_violation(camera_id, item["violation"])

        logger.info(
            "Detect upload | cam=%s loc=%s plates=%s saved=%s",
            camera_id,
            event_location,
            len(detections),
            sum(1 for item in items if item.get("violation_saved")),
        )

        return {
            "success": True,
            "camera_id": camera_id,
            "camera_name": camera.get("camera_name"),
            "location": event_location,
            "captured_at": captured_dt.isoformat(),
            "traffic_light_state": tl_state.value,
            "processing_ms": processing_ms,
            "quality_score": quality_score,
            "detected_count": len(detections),
            "saved_count": sum(1 for item in items if item.get("violation_saved")),
            "items": items,
        }

    def _analyze_frame(
        self,
        *,
        camera_id: int,
        image_bytes: bytes,
        captured_at: Optional[str],
        location: Optional[str],
        traffic_light_state: str,
        operation_mode: str,
    ) -> Dict[str, Any]:
        camera = self._camera_repository.get_by_id(camera_id)
        if camera is None:
            raise ValueError(f"Camera {camera_id} khong ton tai")
        if not image_bytes:
            raise ValueError("Khong co du lieu anh de xu ly")

        frame = self._decode_image(image_bytes)
        captured_dt = self._parse_timestamp(captured_at)
        tl_state = self._parse_traffic_light_state(traffic_light_state)
        event_location = (location or camera.get("location") or "Chua cau hinh").strip()
        zones = self._camera_repository.get_zones(camera_id)

        started = time.perf_counter()
        detections = self._sort_detections(self._get_detector().process_frame(frame))
        detections = self._apply_detection_zones(detections, zones)
        processing_ms = int((time.perf_counter() - started) * 1000)
        quality_score = self._estimate_quality_score(frame)

        for detection in detections:
            detection["vehicle_crop_bbox"] = self._compute_vehicle_bbox(frame, detection["bbox"])
        self._annotate_violation_state(detections, zones, tl_state)

        live_view_store.update_frame(
            camera_id,
            timestamp=captured_dt.astimezone(ZoneInfo(self._settings.timezone)),
            frame_width=int(frame.shape[1]),
            frame_height=int(frame.shape[0]),
            traffic_light_state=tl_state.value,
            operation_mode=operation_mode,
            tl_state_ms=0,
            quality_score=quality_score,
            processing_ms=processing_ms,
            detections=detections,
        )
        self._camera_repository.touch_last_seen(camera_id)

        return {
            "camera": camera,
            "frame": frame,
            "captured_at": captured_dt,
            "traffic_light_state": tl_state,
            "location": event_location,
            "processing_ms": processing_ms,
            "quality_score": quality_score,
            "detections": detections,
            "zones": zones,
        }

    async def _persist_detection(
        self,
        *,
        camera_id: int,
        frame: np.ndarray,
        detection: Dict[str, Any],
        captured_dt: datetime,
        traffic_light_state: TrafficLightState,
        quality_score: float,
        processing_ms: int,
    ) -> Dict[str, Any]:
        bbox = detection["bbox"]
        vehicle_bbox = detection["vehicle_crop_bbox"]
        plate_crop = self._safe_crop(frame, bbox)
        vehicle_crop = self._safe_crop(frame, vehicle_bbox)
        plate_url = await self._image_service.save_plate_image(plate_crop, camera_id)
        vehicle_url = await self._image_service.save_vehicle_image(vehicle_crop, camera_id)
        license_plate = self._normalize_plate(detection.get("plate_text"))
        confidence = float(
            detection.get("overall_confidence")
            or detection.get("ocr_confidence")
            or detection.get("confidence")
            or 0.0
        )

        violation = None
        duplicate = False
        skipped_reason = None

        if detection.get("is_violation"):
            violation = await self._violation_service.create_violation(
                camera_id=camera_id,
                image_url=vehicle_url or "",
                plate_image_url=plate_url,
                license_plate=license_plate,
                confidence=confidence,
                traffic_light_state=traffic_light_state,
                timestamp=captured_dt.astimezone(timezone.utc),
                image_quality_score=quality_score,
                processing_time_ms=processing_ms,
                bbox_x=int(bbox["x1"]),
                bbox_y=int(bbox["y1"]),
                bbox_w=int(bbox["x2"] - bbox["x1"]),
                bbox_h=int(bbox["y2"] - bbox["y1"]),
            )
            duplicate = bool(violation and violation.get("success") is False)
        else:
            skipped_reason = "not_red_light_violation"

        return {
            "license_plate": license_plate,
            "confidence": round(confidence, 4),
            "bbox": bbox,
            "vehicle_crop_bbox": vehicle_bbox,
            "matched_zones": detection.get("matched_zones") or [],
            "matched_stop_lines": detection.get("matched_stop_lines") or [],
            "crossed_stop_line": bool(detection.get("crossed_stop_line")),
            "is_violation": bool(detection.get("is_violation")),
            "vehicle_image_url": vehicle_url,
            "plate_image_url": plate_url,
            "violation_saved": bool(detection.get("is_violation")) and not duplicate,
            "duplicate": duplicate,
            "skipped_reason": skipped_reason,
            "violation": violation,
        }

    @staticmethod
    def _decode_image(image_bytes: bytes) -> np.ndarray:
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            raise ValueError("Khong giai ma duoc JPEG")
        return image

    def _parse_timestamp(self, captured_at: Optional[str]) -> datetime:
        if not captured_at or not captured_at.strip():
            return datetime.now(timezone.utc)

        raw = captured_at.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(self._settings.timezone))
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _parse_traffic_light_state(raw: str) -> TrafficLightState:
        value = (raw or "red").strip().lower()
        try:
            return TrafficLightState(value)
        except ValueError as exc:
            raise ValueError(f"traffic_light_state khong hop le: {raw}") from exc

    @staticmethod
    def _normalize_plate(raw: Optional[str]) -> Optional[str]:
        text = (raw or "").strip().upper().replace(" ", "")
        return text or None

    @staticmethod
    def _sort_detections(detections: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return sorted(detections or [], key=lambda item: int(item["bbox"]["x1"]))

    @staticmethod
    def _safe_crop(image: np.ndarray, bbox: Dict[str, int]) -> np.ndarray:
        height, width = image.shape[:2]
        x1 = max(0, min(int(bbox["x1"]), width - 1))
        y1 = max(0, min(int(bbox["y1"]), height - 1))
        x2 = max(x1 + 1, min(int(bbox["x2"]), width))
        y2 = max(y1 + 1, min(int(bbox["y2"]), height))
        return image[y1:y2, x1:x2]

    def _compute_vehicle_bbox(self, image: np.ndarray, bbox: Dict[str, int]) -> Dict[str, int]:
        frame_h, frame_w = image.shape[:2]
        x1 = int(bbox["x1"])
        y1 = int(bbox["y1"])
        x2 = int(bbox["x2"])
        y2 = int(bbox["y2"])
        plate_w = max(1, x2 - x1)
        plate_h = max(1, y2 - y1)

        pad_x = int(plate_w * self._settings.vehicle_crop_pad_x)
        pad_top = int(plate_h * self._settings.vehicle_crop_pad_top)
        pad_bottom = int(plate_h * self._settings.vehicle_crop_pad_bottom)

        return {
            "x1": max(0, x1 - pad_x),
            "y1": max(0, y1 - pad_top),
            "x2": min(frame_w, x2 + pad_x),
            "y2": min(frame_h, y2 + pad_bottom),
        }

    @staticmethod
    def _apply_detection_zones(detections: list[Dict[str, Any]], zones: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        active_zones = [
            zone for zone in (zones or [])
            if zone.get("active", True) and zone.get("zone_type") in {"detection", "roi"}
        ]
        if not active_zones:
            return detections

        filtered: list[Dict[str, Any]] = []
        for detection in detections:
            bbox = detection.get("bbox") or {}
            cx = (int(bbox.get("x1", 0)) + int(bbox.get("x2", 0))) / 2.0
            cy = (int(bbox.get("y1", 0)) + int(bbox.get("y2", 0))) / 2.0
            matched_zone_names = []
            for zone in active_zones:
                zx = int(zone.get("x", 0))
                zy = int(zone.get("y", 0))
                zw = int(zone.get("width", 0))
                zh = int(zone.get("height", 0))
                if zx <= cx <= zx + zw and zy <= cy <= zy + zh:
                    matched_zone_names.append(zone.get("zone_name") or "zone")

            if matched_zone_names:
                detection["matched_zones"] = matched_zone_names
                filtered.append(detection)

        return filtered

    @staticmethod
    def _annotate_violation_state(
        detections: list[Dict[str, Any]],
        zones: list[Dict[str, Any]],
        traffic_light_state: TrafficLightState,
    ) -> None:
        stop_lines = [
            zone for zone in (zones or [])
            if zone.get("active", True) and zone.get("zone_type") == "stop_line"
        ]
        active_detection_zones = [
            zone for zone in (zones or [])
            if zone.get("active", True) and zone.get("zone_type") in {"detection", "roi"}
        ]
        has_detection_zones = bool(active_detection_zones)
        for detection in detections:
            vehicle_bbox = detection.get("vehicle_crop_bbox") or detection.get("bbox") or {}
            matched_stop_lines = []
            if stop_lines:
                for zone in stop_lines:
                    zone_bbox = {
                        "x1": int(zone.get("x", 0)),
                        "y1": int(zone.get("y", 0)),
                        "x2": int(zone.get("x", 0)) + int(zone.get("width", 0)),
                        "y2": int(zone.get("y", 0)) + int(zone.get("height", 0)),
                    }
                    if DetectionService._bbox_intersects(vehicle_bbox, zone_bbox):
                        matched_stop_lines.append(zone.get("zone_name") or "stop-line")

            crossed_stop_line = bool(matched_stop_lines)
            in_violation_zone = bool(detection.get("matched_zones")) if has_detection_zones else True
            detection["matched_stop_lines"] = matched_stop_lines
            detection["crossed_stop_line"] = crossed_stop_line
            detection["is_violation"] = in_violation_zone and traffic_light_state == TrafficLightState.RED

    @staticmethod
    def _bbox_intersects(a: Dict[str, int], b: Dict[str, int]) -> bool:
        ax1 = int(a.get("x1", 0))
        ay1 = int(a.get("y1", 0))
        ax2 = int(a.get("x2", 0))
        ay2 = int(a.get("y2", 0))
        bx1 = int(b.get("x1", 0))
        by1 = int(b.get("y1", 0))
        bx2 = int(b.get("x2", 0))
        by2 = int(b.get("y2", 0))
        return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)

    @staticmethod
    def _estimate_quality_score(image: np.ndarray) -> float:
        if image is None or image.size == 0:
            return 0.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return round(min(100.0, variance / 12.0), 2)

    def _get_detector(self) -> "LicensePlateDetector":
        if self._detector is None:
            from backend.ml.detector import get_detector

            self._detector = get_detector()
        return self._detector
