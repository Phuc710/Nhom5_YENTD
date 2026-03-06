"""
services/finalize_service.py — Logic xử lý finalize (tách từ api/finalize.py)
Được gọi từ: POST /api/finalize  +  upload.py (emergency auto-finalize)
"""
import os
import time
from datetime import datetime
from typing import List, Dict

from services.buffer_service import frame_buffer
from services.violation_service import ViolationService
from services.image_service import ImageService
from services.voting_service import fuzzy_vote_ocr_results
from database.models import TrafficLightState
from utils.logger import get_logger

logger = get_logger(__name__)

_violation_svc = ViolationService()
_image_svc     = ImageService()


async def finalize_camera(camera_id: int) -> List[Dict]:
    """
    Xử lý tất cả frames đã buffer cho camera:
    1. Lấy frames từ buffer (và clear buffer)
    2. Với mỗi track: vote OCR → tạo vi phạm
    Returns: list of created violation dicts
    """
    start  = time.time()
    frames = frame_buffer.consume_frames(camera_id)

    if not frames:
        logger.info(f"FINALIZE cam={camera_id}: không có frames")
        return []

    logger.info(f"🟢  FINALIZE cam={camera_id}: {len(frames)} frames")

    # Tracking
    tracker      = frame_buffer.get_tracker(camera_id)
    for frame in frames:
        tracker.update(frame.get("detections", []))
    active_tracks = tracker.update([])

    if not active_tracks:
        logger.warning(f"⚠️  FINALIZE cam={camera_id}: không track được xe nào")
        return []

    violations = []
    for track in active_tracks:
        track_id = track["track_id"]

        # Thu thập OCR results từ track
        ocr_results = [
            {
                "license_plate": det.get("plate_text"),
                "confidence":    det.get("confidence", det.get("ocr_confidence", 0)),
                "quality_score": det.get("quality_score", 0),
            }
            for det in track.get("detections", [])
        ]

        # Vote
        vote = fuzzy_vote_ocr_results(ocr_results, threshold=1)
        if not vote:
            continue

        min_votes = max(1, len(ocr_results) // 2)
        if vote["vote_count"] < min_votes:
            logger.warning(f"⚠️  Track {track_id}: votes {vote['vote_count']}/{min_votes} — skipped")
            continue

        # Tìm best detection
        dets = track.get("detections", [])
        best_det   = max(dets, key=lambda d: d.get("confidence", 0)) if dets else {}

        # Tìm frame chứa best detection
        best_frame = frames[0]
        for f in frames:
            for d in f.get("detections", []):
                if d.get("plate_text") == best_det.get("plate_text"):
                    best_frame = f
                    break

        # Crop biển số
        plate_path  = None
        bbox_x = bbox_y = bbox_w = bbox_h = None
        try:
            bbox     = best_det.get("bbox", {})
            x1, y1 = bbox.get("x1", 0), bbox.get("y1", 0)
            x2, y2 = bbox.get("x2", 0), bbox.get("y2", 0)
            if x2 > x1 and y2 > y1:
                plate_img  = best_frame["image"][y1:y2, x1:x2]
                plate_path = await _image_svc.save_plate_image(plate_img, camera_id)
                bbox_x, bbox_y, bbox_w, bbox_h = x1, y1, x2 - x1, y2 - y1
        except Exception as e:
            logger.error(f"❌  Crop plate failed track={track_id}: {e}")

        # Tạo vi phạm
        proc_ms = int((time.time() - start) * 1000)
        try:
            result = await _violation_svc.create_violation(
                camera_id           = camera_id,
                image_url           = f"/uploads/original/{os.path.basename(best_frame['image_path'])}",
                plate_image_url     = f"/uploads/detected_plates/{os.path.basename(plate_path)}" if plate_path else None,
                license_plate       = vote["license_plate"],
                confidence          = vote["avg_confidence"],
                traffic_light_state = TrafficLightState.RED,
                timestamp           = best_frame["timestamp"],
                vote_count          = vote["vote_count"],
                vote_percent        = vote["vote_percent"],
                total_frames        = vote["total_frames"],
                track_id            = track_id,
                image_quality_score = best_frame.get("quality_score"),
                processing_time_ms  = proc_ms,
                bbox_x              = bbox_x,
                bbox_y              = bbox_y,
                bbox_w              = bbox_w,
                bbox_h              = bbox_h,
            )
            if result.get("id"):
                violations.append(result)
        except Exception as e:
            logger.error(f"❌  Create violation failed track={track_id}: {e}")

    logger.info(f"🎉  FINALIZE cam={camera_id}: {len(violations)} vi phạm tạo xong trong {int((time.time()-start)*1000)}ms")
    return violations
