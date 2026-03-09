"""
POST /api/finalize.
ESP32 gọi khi đèn chuyển xanh để chốt vi phạm từ buffer đã tích lũy.
"""

import time

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse

from services.finalize_service import finalize_camera
from utils.logger import get_logger

router = APIRouter(tags=["Upload"])
logger = get_logger(__name__)


@router.post("/finalize")
async def finalize_violations(camera_id: int = Form(...)):
    """Chốt vi phạm của một camera sau khi kết thúc pha đèn đỏ."""
    start = time.time()
    try:
        violations = await finalize_camera(camera_id)
        ms = int((time.time() - start) * 1000)

        if not violations:
            return JSONResponse(
                {
                    "success": True,
                    "message": "Không tạo vi phạm mới",
                    "camera_id": camera_id,
                    "ms": ms,
                }
            )

        return JSONResponse(
            {
                "success": True,
                "message": f"Đã tạo {len(violations)} vi phạm",
                "violations": violations,
                "camera_id": camera_id,
                "ms": ms,
            }
        )
    except Exception as exc:
        logger.error("Lỗi finalize camera=%s: %s", camera_id, exc)
        raise HTTPException(500, str(exc))
