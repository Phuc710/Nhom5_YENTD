"""
Nhận frame từ ESP32-S3-CAM.
POST /api/upload: buffer frame pha đỏ và OCR.
POST /api/upload/heartbeat: cập nhật last_seen của camera.
"""

import time
from datetime import datetime

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config.settings import get_settings
from services.buffer_service import frame_buffer
from services.image_service import ImageService
from services.quality_service import calculate_quality_score
from utils.logger import get_logger

router = APIRouter()
_img_svc = ImageService()
logger = get_logger(__name__)
settings = get_settings()
_VALID_TRAFFIC_STATES = {"red", "yellow", "green"}
_VALID_OPERATION_MODES = {"normal", "emergency_red", "emergency_green"}


@router.post("/upload")
async def upload_frame(
    file: UploadFile = File(...),
    camera_id: int = Form(...),
    traffic_light_state: str = Form(...),
    operation_mode: str = Form(default="normal"),
    tl_state_ms: int = Form(default=0),
    timestamp: str = Form(default=None),
    emergency: bool = Form(default=False),
):
    """
    Nhận frame JPEG từ ESP32.

    Flow:
    - ESP32 gửi frame khi đèn đỏ để buffer và OCR.
    - Khi đèn chuyển xanh, ESP32 gọi `/api/finalize` để chốt vi phạm.
    - `emergency=True` cho phép chốt ngay, không chờ đủ buffer.
    """
    start = time.time()
    try:
        traffic_light_state = _normalize_traffic_light_state(traffic_light_state)
        operation_mode = _normalize_operation_mode(operation_mode)

        if traffic_light_state != "red":
            _update_heartbeat(camera_id)
            elapsed = int((time.time() - start) * 1000)
            logger.info(
                "Bỏ qua frame camera=%s state=%s mode=%s",
                camera_id,
                traffic_light_state,
                operation_mode,
            )
            return JSONResponse(
                {
                    "success": True,
                    "skipped": True,
                    "reason": "non_red_light",
                    "camera_id": camera_id,
                    "traffic_light_state": traffic_light_state,
                    "operation_mode": operation_mode,
                    "tl_state_ms": tl_state_ms,
                    "processing_ms": elapsed,
                }
            )

        ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now()

        raw = await file.read()
        arr = np.frombuffer(raw, np.uint8)

        import cv2

        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Không thể giải mã ảnh JPEG")

        quality = calculate_quality_score(image)
        if quality["overall_score"] < settings.quality_threshold:
            logger.info(
                "Loại frame chất lượng thấp camera=%s score=%.1f",
                camera_id,
                quality["overall_score"],
            )
            return JSONResponse(
                {
                    "success": True,
                    "skipped": True,
                    "reason": f"low_quality ({quality['overall_score']:.1f})",
                    "camera_id": camera_id,
                }
            )

        image_path = await _img_svc.save_image(raw, camera_id, "original")

        from ml.detector import get_detector

        detector = get_detector()
        detections = detector.process_image(image_path)

        frame_data = {
            "image": image,
            "image_path": image_path,
            "detections": detections,
            "quality_score": quality["overall_score"],
            "timestamp": ts,
            "traffic_light_state": traffic_light_state,
            "operation_mode": operation_mode,
            "tl_state_ms": tl_state_ms,
        }
        frame_buffer.add_frame(camera_id, frame_data, emergency=emergency)

        _update_heartbeat(camera_id)

        should_finalize, finalize_reason = frame_buffer.should_process(camera_id)
        auto_finalized = False
        violations_created = []
        if should_finalize and (
            emergency or finalize_reason.startswith("high_confidence")
        ):
            from services.finalize_service import finalize_camera

            violations_created = await finalize_camera(camera_id)
            auto_finalized = True
            logger.info(
                "Auto finalize camera=%s reason=%s violations=%s",
                camera_id,
                finalize_reason,
                len(violations_created),
            )

        elapsed = int((time.time() - start) * 1000)
        logger.info(
            "Đã buffer frame camera=%s detections=%s quality=%.0f processing_ms=%s",
            camera_id,
            len(detections),
            quality["overall_score"],
            elapsed,
        )

        return JSONResponse(
            {
                "success": True,
                "camera_id": camera_id,
                "detections": len(detections),
                "quality_score": quality["overall_score"],
                "frames_buffered": len(frame_buffer.get_frames(camera_id)),
                "auto_finalized": auto_finalized,
                "violations": violations_created,
                "traffic_light_state": traffic_light_state,
                "operation_mode": operation_mode,
                "tl_state_ms": tl_state_ms,
                "finalize_reason": finalize_reason,
                "processing_ms": elapsed,
            }
        )

    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("Lỗi upload camera=%s: %s", camera_id, exc)
        raise HTTPException(500, str(exc))


@router.post("/upload/heartbeat")
async def heartbeat(camera_id: int = Form(...)):
    """Cập nhật thời điểm online gần nhất của camera."""
    _update_heartbeat(camera_id)
    return {"success": True, "camera_id": camera_id}


def _update_heartbeat(camera_id: int) -> None:
    try:
        from repositories.camera_repo import CameraRepository

        CameraRepository().touch_last_seen(camera_id)
    except Exception as exc:
        logger.debug("Không cập nhật được heartbeat camera=%s: %s", camera_id, exc)


def _normalize_traffic_light_state(state: str) -> str:
    value = str(state or "").strip().lower()
    if value not in _VALID_TRAFFIC_STATES:
        raise ValueError(f"traffic_light_state không hợp lệ: {state}")
    return value


def _normalize_operation_mode(mode: str) -> str:
    value = str(mode or "normal").strip().lower()
    if value not in _VALID_OPERATION_MODES:
        raise ValueError(f"operation_mode không hợp lệ: {mode}")
    return value
