"""
Violation routes: CRUD for traffic violations and OCR results.
Includes image upload with WebP compression.

All DB/image calls run on thread pool via asyncio.to_thread() — non-blocking.
"""
import asyncio
import base64
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from api.models import ViolationCreateRequest, OCRResultRequest, MessageResponse
from api.services.db_service import DBService
from api.services.image_service import ImageService
from api.dependencies import get_db_service, get_image_service

router = APIRouter(prefix="/violations", tags=["Violations"])


def _require_db(db: DBService):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

@router.get("", summary="List violations")
async def list_violations(
    camera_id: Optional[int] = Query(default=None),
    license_plate: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    return await asyncio.to_thread(
        db.list_violations,
        camera_id=camera_id,
        license_plate=license_plate,
        limit=limit,
        offset=offset,
    )


@router.get("/stats/daily", summary="Daily violation statistics")
async def daily_stats(
    camera_id: Optional[int] = Query(default=None),
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    return await asyncio.to_thread(db.get_daily_stats, camera_id=camera_id)


@router.get("/{violation_id}", summary="Get violation detail")
async def get_violation(
    violation_id: int,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    violation = await asyncio.to_thread(db.get_violation, violation_id)
    if violation is None:
        raise HTTPException(status_code=404, detail=f"Violation {violation_id} not found.")
    return violation


# ---------------------------------------------------------------------------
# CREATE — JSON (URLs already known, e.g. from local pipeline)
# ---------------------------------------------------------------------------

@router.post("", response_model=MessageResponse, summary="Record a violation (JSON)", status_code=201)
async def create_violation(
    request: ViolationCreateRequest,
    db: DBService = Depends(get_db_service),
):
    """Record a violation where image URLs are already known (pre-uploaded)."""
    _require_db(db)
    result = await asyncio.to_thread(db.create_violation, request.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to record violation.")
    return MessageResponse(message=f"Violation recorded (id={result.get('id', '?')}).")


# ---------------------------------------------------------------------------
# CREATE WITH IMAGES — multipart upload, compress → WebP → Supabase Storage
# ---------------------------------------------------------------------------

@router.post(
    "/with-images",
    summary="Record violation + upload images as WebP",
    description=(
        "Upload raw frame images (JPEG/PNG). Backend compresses to **WebP**, "
        "uploads to Supabase Storage, and records the violation with final URLs. "
        "Returns violation ID and all image URLs."
    ),
    status_code=201,
)
async def create_violation_with_images(
    # ── Violation metadata (form fields) ──
    camera_id: int = Form(...),
    timestamp: str = Form(..., description="ISO 8601 UTC"),
    violation_type: str = Form(default="red_light"),
    traffic_light_state: str = Form(default="red"),
    license_plate: Optional[str] = Form(default=None),
    confidence: Optional[float] = Form(default=None),
    track_id: Optional[int] = Form(default=None),

    # Bbox for server-side cropping (optional — crop done here for speed)
    vehicle_x1: Optional[int] = Form(default=None),
    vehicle_y1: Optional[int] = Form(default=None),
    vehicle_x2: Optional[int] = Form(default=None),
    vehicle_y2: Optional[int] = Form(default=None),
    plate_x1: Optional[int] = Form(default=None),
    plate_y1: Optional[int] = Form(default=None),
    plate_x2: Optional[int] = Form(default=None),
    plate_y2: Optional[int] = Form(default=None),

    # ── Images (raw frame bytes) ──
    full_frame: UploadFile = File(..., description="Full frame at violation moment"),

    # ── Services ──
    db: DBService = Depends(get_db_service),
    img: ImageService = Depends(get_image_service),
):
    _require_db(db)

    # 1. Read uploaded frame bytes (async I/O)
    raw_bytes = await full_frame.read()

    # 2. Decode + compress + upload WebP (on thread pool — CPU + network)
    def _process_and_upload():
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Cannot decode uploaded image")

        vehicle_bbox = None
        if all(v is not None for v in [vehicle_x1, vehicle_y1, vehicle_x2, vehicle_y2]):
            vehicle_bbox = (vehicle_x1, vehicle_y1, vehicle_x2, vehicle_y2)

        plate_bbox = None
        if all(v is not None for v in [plate_x1, plate_y1, plate_x2, plate_y2]):
            plate_bbox = (plate_x1, plate_y1, plate_x2, plate_y2)

        return img.process_violation_images(
            frame=frame,
            vehicle_bbox=vehicle_bbox,
            plate_bbox=plate_bbox,
            camera_id=camera_id,
            track_id=track_id or 0,
        )

    try:
        urls = await asyncio.to_thread(_process_and_upload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Build violation record
    violation_data = {
        "camera_id": camera_id,
        "timestamp": timestamp,
        "violation_type": violation_type,
        "traffic_light_state": traffic_light_state,
        "full_image_url": urls.get("full_image_url") or "",
        "cropped_vehicle_url": urls.get("cropped_vehicle_url"),
        "cropped_plate_url": urls.get("cropped_plate_url"),
    }
    if license_plate:
        violation_data["license_plate"] = license_plate
    if confidence is not None:
        violation_data["confidence"] = confidence
    if track_id is not None:
        violation_data["track_id"] = track_id
    if vehicle_x1 is not None:
        violation_data.update({
            "bbox_x": vehicle_x1, "bbox_y": vehicle_y1,
            "bbox_w": (vehicle_x2 or 0) - (vehicle_x1 or 0),
            "bbox_h": (vehicle_y2 or 0) - (vehicle_y1 or 0),
        })

    # 4. Insert DB record (on thread pool)
    result = await asyncio.to_thread(db.create_violation, violation_data)
    if result is None:
        raise HTTPException(status_code=400, detail="Images uploaded but failed to record violation in DB.")

    return {
        "id": result.get("id"),
        "message": "Violation recorded with WebP images.",
        **urls,
    }


# ---------------------------------------------------------------------------
# CREATE — base64 batch (internal pipeline use: fast, no multipart overhead)
# ---------------------------------------------------------------------------

@router.post(
    "/with-images/b64",
    summary="Record violation + upload images (base64 JSON)",
    description=(
        "JSON body with base64-encoded images. Faster than multipart for internal "
        "pipeline use (no form-data parsing overhead). Backend compresses to WebP."
    ),
    status_code=201,
)
async def create_violation_b64(
    request: dict,
    db: DBService = Depends(get_db_service),
    img: ImageService = Depends(get_image_service),
):
    _require_db(db)

    camera_id = request.get("camera_id", 0)
    track_id = request.get("track_id", 0)
    timestamp = request.get("timestamp", "")
    full_b64 = request.get("full_frame_b64")

    if not full_b64 or not timestamp:
        raise HTTPException(status_code=400, detail="full_frame_b64 and timestamp are required.")

    def _process():
        raw = base64.b64decode(full_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Cannot decode base64 image")

        vbbox = request.get("vehicle_bbox")  # [x1,y1,x2,y2] or null
        pbbox = request.get("plate_bbox")

        return img.process_violation_images(
            frame=frame,
            vehicle_bbox=tuple(vbbox) if vbbox else None,
            plate_bbox=tuple(pbbox) if pbbox else None,
            camera_id=camera_id,
            track_id=track_id,
        )

    try:
        urls = await asyncio.to_thread(_process)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    violation_data = {
        "camera_id": camera_id,
        "timestamp": timestamp,
        "violation_type": request.get("violation_type", "red_light"),
        "traffic_light_state": request.get("traffic_light_state", "red"),
        "full_image_url": urls.get("full_image_url") or "",
        "cropped_vehicle_url": urls.get("cropped_vehicle_url"),
        "cropped_plate_url": urls.get("cropped_plate_url"),
        **{k: v for k, v in {
            "license_plate": request.get("license_plate"),
            "confidence": request.get("confidence"),
            "track_id": request.get("track_id"),
            "vote_count": request.get("vote_count"),
            "vote_percent": request.get("vote_percent"),
            "processing_time_ms": request.get("processing_time_ms"),
        }.items() if v is not None},
    }

    result = await asyncio.to_thread(db.create_violation, violation_data)
    if result is None:
        raise HTTPException(status_code=400, detail="Images uploaded but DB insert failed.")

    return {"id": result.get("id"), "message": "Violation recorded.", **urls}


# ---------------------------------------------------------------------------
# OCR results
# ---------------------------------------------------------------------------

@router.post("/{violation_id}/ocr", response_model=MessageResponse, summary="Add OCR result")
async def add_ocr_result(
    violation_id: int,
    request: OCRResultRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    data = request.model_dump(exclude_none=True)
    data["violation_id"] = violation_id
    result = await asyncio.to_thread(db.create_ocr_result, data)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to add OCR result.")
    return MessageResponse(message="OCR result added.")


# ---------------------------------------------------------------------------
# Snapshot — get current frame as WebP
# ---------------------------------------------------------------------------

@router.get(
    "/snapshot/webp",
    summary="Get current stream frame as WebP",
    description="Returns current frame from active stream, compressed to WebP. Fast preview.",
    responses={200: {"content": {"image/webp": {}}}},
)
async def get_snapshot_webp(
    quality: int = Query(default=80, ge=10, le=100, description="WebP quality 10-100"),
    img: ImageService = Depends(get_image_service),
):
    """Returns current stream frame as WebP image."""
    from fastapi.responses import Response
    from api.dependencies import stream_manager

    if not stream_manager.is_active:
        raise HTTPException(status_code=409, detail="No active stream.")

    frame = stream_manager.get_current_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available yet.")

    webp_bytes = await asyncio.to_thread(img.encode_frame_webp, frame, quality=quality)
    if webp_bytes is None:
        raise HTTPException(status_code=500, detail="WebP encoding failed.")

    return Response(content=webp_bytes, media_type="image/webp")
