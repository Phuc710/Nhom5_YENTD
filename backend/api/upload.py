"""
api/upload.py — Nhận frame từ ESP32-S3-CAM
POST /api/upload — Buffer + OCR frames (khi đèn đỏ)
POST /api/upload/heartbeat — Cập nhật last_seen camera
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import time
import os
import numpy as np

from services.buffer_service import frame_buffer
from services.image_service import ImageService
from services.quality_service import calculate_quality_score
from utils.logger import get_logger

router  = APIRouter()
_img_svc = ImageService()
logger  = get_logger(__name__)


@router.post("/upload")
async def upload_frame(
    file:                UploadFile = File(...),
    camera_id:           int        = Form(...),
    traffic_light_state: str        = Form(...),        # red | yellow | green
    timestamp:           str        = Form(default=None),
    emergency:           bool       = Form(default=False),
):
    """
    Nhận frame JPEG từ ESP32.

    Flow:
    - ESP32 gửi frame khi đèn ĐỎ → Buffer + OCR, KHÔNG tạo vi phạm.
    - Khi đèn XANH: ESP32 gọi POST /api/finalize → Vote + tạo vi phạm.

    emergency=True → bypass frame count check, process ngay.
    """
    start = time.time()
    try:
        ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now()

        # Decode image
        raw   = await file.read()
        arr   = np.frombuffer(raw, np.uint8)
        import cv2
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Không thể decode ảnh — file không hợp lệ")

        # Quality check
        quality = calculate_quality_score(image)
        if quality["overall_score"] < 70:
            logger.info(f"Low quality frame rejected cam={camera_id} score={quality['overall_score']:.1f}")
            return JSONResponse({"success": True, "skipped": True,
                                 "reason": f"low_quality ({quality['overall_score']:.1f})",
                                 "camera_id": camera_id})

        # Save to disk
        image_path = await _img_svc.save_image(raw, camera_id, "original")

        # Detect license plates + OCR
        from ml.detector import get_detector
        detector   = get_detector()
        detections = detector.process_image(image_path)

        # Buffer frame
        frame_data = {
            "image":               image,
            "image_path":          image_path,
            "detections":          detections,
            "quality_score":       quality["overall_score"],
            "timestamp":           ts,
            "traffic_light_state": traffic_light_state,
        }
        frame_buffer.add_frame(camera_id, frame_data, emergency=emergency)

        # Update heartbeat (last_seen)
        _update_heartbeat(camera_id)

        # Check if should auto-finalize (emergency or timeout)
        should, reason = frame_buffer.should_process(camera_id)
        auto_finalized = False
        violations_created = []
        if should and emergency:
            # Finalize inline
            from services.finalize_service import finalize_camera
            violations_created = await finalize_camera(camera_id)
            auto_finalized = True

        elapsed = int((time.time() - start) * 1000)
        logger.info(f"✅  Frame buffered cam={camera_id} dets={len(detections)} q={quality['overall_score']:.0f} {elapsed}ms")

        return JSONResponse({
            "success":           True,
            "camera_id":         camera_id,
            "detections":        len(detections),
            "quality_score":     quality["overall_score"],
            "frames_buffered":   len(frame_buffer.get_frames(camera_id)),
            "auto_finalized":    auto_finalized,
            "violations":        violations_created,
            "processing_ms":     elapsed,
        })

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"❌  Upload error cam={camera_id}: {e}")
        raise HTTPException(500, str(e))


@router.post("/upload/heartbeat")
async def heartbeat(camera_id: int = Form(...)):
    """Cập nhật last_seen của camera — gọi khi thiết bị online"""
    _update_heartbeat(camera_id)
    return {"success": True, "camera_id": camera_id}


def _update_heartbeat(camera_id: int):
    try:
        from repositories.camera_repo import CameraRepository
        CameraRepository().touch_last_seen(camera_id)
    except Exception as e:
        logger.debug(f"Heartbeat failed cam={camera_id}: {e}")
