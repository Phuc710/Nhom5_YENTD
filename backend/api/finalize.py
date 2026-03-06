"""
api/finalize.py — POST /api/finalize — Gọi khi đèn chuyển XANH
ESP32 gọi endpoint này để trigger vote + tạo vi phạm từ buffer đã tích lũy.
"""
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
import time

from services.finalize_service import finalize_camera
from utils.logger import get_logger

router = APIRouter(tags=["Upload"])
logger = get_logger(__name__)


@router.post("/finalize")
async def finalize_violations(camera_id: int = Form(...)):
    """
    Khi đèn giao thông chuyển XANH → ESP32 gọi endpoint này.
    Backend vote tất cả frames đã buffer → tạo violations → clear buffer.
    """
    start = time.time()
    try:
        violations = await finalize_camera(camera_id)
        ms = int((time.time() - start) * 1000)

        if not violations:
            return JSONResponse({
                "success":   True,
                "message":   "No violations created",
                "camera_id": camera_id,
                "ms":        ms,
            })

        return JSONResponse({
            "success":    True,
            "message":    f"Created {len(violations)} violation(s)",
            "violations": violations,
            "camera_id":  camera_id,
            "ms":         ms,
        })

    except Exception as e:
        logger.error(f"❌  Finalize failed cam={camera_id}: {e}")
        raise HTTPException(500, str(e))
