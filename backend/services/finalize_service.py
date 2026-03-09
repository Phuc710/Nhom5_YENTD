"""
Nghiệp vụ finalize.
Được gọi từ POST /api/finalize và luồng auto-finalize trong upload.
"""

import os
import time
from typing import Dict, List

from config.settings import get_settings
from database.models import TrafficLightState
from services.buffer_service import frame_buffer
from services.image_service import ImageService
from services.violation_service import ViolationService
from services.voting_service import fuzzy_vote_ocr_results
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_violation_svc = ViolationService()
_image_svc = ImageService()


def _detection_confidence(detection: Dict) -> float:
    return float(
        detection.get("overall_confidence")
        or detection.get("ocr_confidence")
        or detection.get("confidence")
        or 0.0
    )


async def finalize_camera(camera_id: int) -> List[Dict]:
    """Chốt toàn bộ frame của một pha đèn đỏ thành hồ sơ vi phạm."""
    start = time.time()
    frames = frame_buffer.consume_frames(camera_id)

    if not frames:
        logger.info("Finalize camera=%s: không có frame", camera_id)
        return []

    logger.info(
        "Bắt đầu finalize camera=%s theo pha đèn đỏ với %s frame",
        camera_id,
        len(frames),
    )

    tracker = frame_buffer.get_tracker(camera_id)
    for frame in frames:
        tracker.update(frame.get("detections", []))
    active_tracks = tracker.update([])

    if not active_tracks:
        logger.warning("Finalize camera=%s: không có track hợp lệ", camera_id)
        return []

    violations = []
    for track in active_tracks:
        track_id = track["track_id"]
        ocr_results = [
            {
                "license_plate": detection.get("plate_text"),
                "confidence": _detection_confidence(detection),
                "quality_score": detection.get("quality_score", 0),
            }
            for detection in track.get("detections", [])
            if detection.get("plate_text")
        ]

        if not ocr_results:
            logger.info("Bỏ track=%s vì không có OCR hợp lệ", track_id)
            continue

        vote = fuzzy_vote_ocr_results(
            ocr_results,
            threshold=settings.vote_fuzzy_distance,
        )
        if not vote:
            continue

        has_min_votes = vote["vote_count"] >= settings.min_vote_count
        has_strong_confidence = vote["avg_confidence"] >= settings.vote_confidence_threshold
        if not (has_min_votes or has_strong_confidence):
            logger.warning(
                "Bỏ track=%s vì vote=%s và confidence=%.2f chưa đạt ngưỡng",
                track_id,
                vote["vote_count"],
                vote["avg_confidence"],
            )
            continue

        detections = track.get("detections", [])
        best_detection = max(detections, key=_detection_confidence) if detections else {}

        best_frame = frames[0]
        for frame in frames:
            for detection in frame.get("detections", []):
                if detection.get("plate_text") == best_detection.get("plate_text"):
                    best_frame = frame
                    break

        plate_path = None
        bbox_x = bbox_y = bbox_w = bbox_h = None
        try:
            bbox = best_detection.get("bbox", {})
            x1, y1 = bbox.get("x1", 0), bbox.get("y1", 0)
            x2, y2 = bbox.get("x2", 0), bbox.get("y2", 0)
            if x2 > x1 and y2 > y1:
                plate_img = best_frame["image"][y1:y2, x1:x2]
                plate_path = await _image_svc.save_plate_image(plate_img, camera_id)
                bbox_x, bbox_y, bbox_w, bbox_h = x1, y1, x2 - x1, y2 - y1
        except Exception as exc:
            logger.error("Lỗi cắt biển số track=%s: %s", track_id, exc)

        processing_ms = int((time.time() - start) * 1000)
        try:
            result = await _violation_svc.create_violation(
                camera_id=camera_id,
                image_url=f"/uploads/original/{os.path.basename(best_frame['image_path'])}",
                plate_image_url=(
                    f"/uploads/detected_plates/{os.path.basename(plate_path)}"
                    if plate_path
                    else None
                ),
                license_plate=vote["license_plate"],
                confidence=vote["avg_confidence"],
                traffic_light_state=TrafficLightState.RED,
                timestamp=best_frame["timestamp"],
                vote_count=vote["vote_count"],
                vote_percent=vote["vote_percent"],
                total_frames=vote["total_frames"],
                track_id=track_id,
                image_quality_score=best_frame.get("quality_score"),
                processing_time_ms=processing_ms,
                bbox_x=bbox_x,
                bbox_y=bbox_y,
                bbox_w=bbox_w,
                bbox_h=bbox_h,
            )
            if result.get("id"):
                violations.append(result)
                logger.info(
                    "Chốt vi phạm camera=%s track=%s biển=%s vote=%s confidence=%.2f",
                    camera_id,
                    track_id,
                    vote["license_plate"],
                    vote["vote_count"],
                    vote["avg_confidence"],
                )
        except Exception as exc:
            logger.error("Lỗi tạo vi phạm track=%s: %s", track_id, exc)

    logger.info(
        "Hoàn tất finalize camera=%s violations=%s processing_ms=%s",
        camera_id,
        len(violations),
        int((time.time() - start) * 1000),
    )
    return violations
