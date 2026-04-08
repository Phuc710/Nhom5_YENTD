"""
Evidence API — Violation evidence images + detail for web & mobile.

1 router, 1 code, works for everyone:
  - Web dashboard: full detail + all 3 images
  - Mobile app: list with thumbnails, tap → evidence detail
  - Third party: machine-readable JSON, standardized schema

Design principles:
  - Self-contained responses (no need for extra calls)
  - Strongly typed (Pydantic schemas)
  - Consistent pagination
  - Non-blocking (asyncio.to_thread for all I/O)
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.schemas.evidence import (
    ViolationEvidenceResponse,
    ViolationListResponse,
    ViolationListItem,
    EvidenceImages,
    ImageVariant,
    VehicleInfo,
    PlateInfo,
    CameraRef,
    BBoxPixel,
)
from api.services.db_service import DBService
from api.services.image_service import ImageService
from api.dependencies import get_db_service, get_image_service

router = APIRouter(prefix="/evidence", tags=["Evidence"])


# ---------------------------------------------------------------------------
# Helpers — assemble typed responses from raw DB dicts
# ---------------------------------------------------------------------------

def _build_list_item(row: dict) -> ViolationListItem:
    """Convert DB row → compact list card."""
    return ViolationListItem(
        id=row["id"],
        timestamp=row.get("timestamp", ""),
        timestamp_vn=row.get("timestamp_vn"),
        violation_type=row.get("violation_type", "red_light"),
        traffic_light_state=row.get("traffic_light_state", "red"),
        license_plate=row.get("license_plate"),
        confidence=row.get("confidence"),
        # Thumbnail = vehicle crop (has red bbox overlay — clear to see)
        thumbnail_url=row.get("cropped_vehicle_url") or row.get("full_image_url"),
        camera_id=row.get("camera_id", 0),
        camera_name=row.get("camera_name"),
        camera_location=row.get("location"),
    )


def _build_evidence_response(row: dict) -> ViolationEvidenceResponse:
    """Convert DB row → full evidence response with all images."""
    # Images
    images = EvidenceImages(
        original=ImageVariant(url=row["full_image_url"]) if row.get("full_image_url") else None,
        vehicle=ImageVariant(url=row["cropped_vehicle_url"]) if row.get("cropped_vehicle_url") else None,
        plate=ImageVariant(url=row["cropped_plate_url"]) if row.get("cropped_plate_url") else None,
    )

    # Vehicle bbox (stored as bbox_x/y/w/h in DB)
    bbox = None
    if row.get("bbox_x") is not None:
        x, y = row.get("bbox_x", 0), row.get("bbox_y", 0)
        w, h = row.get("bbox_w", 0), row.get("bbox_h", 0)
        bbox = BBoxPixel(x1=x, y1=y, x2=x + w, y2=y + h, width=w, height=h)

    return ViolationEvidenceResponse(
        id=row["id"],
        timestamp=row.get("timestamp", ""),
        timestamp_vn=row.get("timestamp_vn"),
        violation_type=row.get("violation_type", "red_light"),
        traffic_light_state=row.get("traffic_light_state", "red"),
        camera=CameraRef(
            id=row.get("camera_id", 0),
            name=row.get("camera_name"),
            location=row.get("location"),
        ),
        vehicle=VehicleInfo(
            type=row.get("vehicle_type"),
            track_id=row.get("track_id"),
            bbox=bbox,
        ),
        plate=PlateInfo(
            text=row.get("license_plate"),
            confidence=row.get("confidence"),
            vote_count=row.get("vote_count"),
            vote_percent=row.get("vote_percent"),
        ),
        images=images,
        processing_time_ms=row.get("processing_time_ms"),
        image_quality_score=row.get("image_quality_score"),
    )


# ---------------------------------------------------------------------------
# LIST — violations feed with thumbnails
# ---------------------------------------------------------------------------

@router.get(
    "/violations",
    response_model=ViolationListResponse,
    summary="List violations (web + mobile feed)",
    description=(
        "Paginated violation feed. Each item has a **thumbnail_url** (vehicle crop) "
        "ready for display. Call `GET /evidence/violations/{id}` for full evidence detail.\n\n"
        "**Mobile**: use `limit=20`. **Web**: use `limit=50`."
    ),
)
async def list_violations_evidence(
    camera_id: Optional[int] = Query(default=None, description="Filter by camera"),
    license_plate: Optional[str] = Query(default=None, description="Search plate (partial)"),
    violation_type: Optional[str] = Query(default=None, description="Filter by type"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: DBService = Depends(get_db_service),
):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")

    rows = await asyncio.to_thread(
        db.list_violations,
        camera_id=camera_id,
        license_plate=license_plate,
        limit=limit,
        offset=offset,
    )

    items = [_build_list_item(r) for r in rows]
    return ViolationListResponse(
        items=items,
        total=len(items),   # TODO: add count query to DB service
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


# ---------------------------------------------------------------------------
# DETAIL — full evidence, all images
# ---------------------------------------------------------------------------

@router.get(
    "/violations/{violation_id}",
    response_model=ViolationEvidenceResponse,
    summary="Get violation evidence detail (web + mobile)",
    description=(
        "Returns **complete evidence** for a violation in one call:\n\n"
        "- `images.original` — Full frame, **NO overlay**. Raw legal evidence.\n"
        "- `images.vehicle`  — Vehicle **crop + red bounding box** + plate text label.\n"
        "- `images.plate`    — **License plate enlarged** + yellow border + text below.\n\n"
        "All images are **WebP** for fast loading. URLs are public (Supabase Storage)."
    ),
)
async def get_violation_evidence(
    violation_id: int,
    db: DBService = Depends(get_db_service),
):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")

    row = await asyncio.to_thread(db.get_violation, violation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Violation {violation_id} not found.")

    return _build_evidence_response(row)


# ---------------------------------------------------------------------------
# IMAGE PROXY — serve images directly (for local storage fallback)
# ---------------------------------------------------------------------------

@router.get(
    "/violations/{violation_id}/image/{image_type}",
    summary="Get evidence image directly",
    description=(
        "Serve a specific image type directly from the API.\n\n"
        "**image_type**: `original`, `vehicle`, `plate`\n\n"
        "Use this when images are stored **locally** (not Supabase). "
        "For Supabase storage, use the `images.*.url` from the evidence response."
    ),
    responses={
        200: {"content": {"image/webp": {}, "image/jpeg": {}}},
    },
)
async def get_evidence_image(
    violation_id: int,
    image_type: str,
    db: DBService = Depends(get_db_service),
):
    from pathlib import Path

    if image_type not in ("original", "vehicle", "plate"):
        raise HTTPException(
            status_code=400,
            detail="image_type must be one of: original, vehicle, plate",
        )
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")

    row = await asyncio.to_thread(db.get_violation, violation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Violation {violation_id} not found.")

    url_map = {
        "original": row.get("full_image_url"),
        "vehicle":  row.get("cropped_vehicle_url"),
        "plate":    row.get("cropped_plate_url"),
    }
    url = url_map[image_type]
    if not url:
        raise HTTPException(status_code=404, detail=f"No {image_type} image for violation {violation_id}.")

    # If URL is a local path (/violations/images/{type}/{filename}), serve from disk
    if url.startswith("/violations/images/"):
        # Strip prefix → e.g. "original/1744123456_abc_t7.webp"
        relative = url.removeprefix("/violations/images/")
        local_path = Path("data/violations") / relative
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found on disk.")
        content = await asyncio.to_thread(local_path.read_bytes)
        media_type = "image/webp" if local_path.suffix == ".webp" else "image/jpeg"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )


    # Supabase URL — redirect client
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url, status_code=302)


# ---------------------------------------------------------------------------
# SNAPSHOT — live frame as WebP (no violation needed)
# ---------------------------------------------------------------------------

@router.get(
    "/snapshot/{camera_id}",
    summary="Live snapshot from camera as WebP",
    description=(
        "Returns **current frame** from active camera stream as WebP.\n\n"
        "Used for: live preview thumbnail, quick check without MJPEG.\n"
        "Returns 409 if stream not active."
    ),
    responses={200: {"content": {"image/webp": {}}}},
)
async def camera_snapshot(
    camera_id: int,
    quality: int = Query(default=80, ge=10, le=100),
    img: ImageService = Depends(get_image_service),
):
    from api.dependencies import stream_manager

    if not stream_manager.is_active:
        raise HTTPException(
            status_code=409,
            detail=f"No active stream for camera {camera_id}. Start via POST /stream/start.",
        )

    frame = await asyncio.to_thread(stream_manager.get_current_frame)
    if frame is None:
        raise HTTPException(status_code=503, detail="Stream active but no frame yet.")

    webp = await asyncio.to_thread(img.encode_frame_webp, frame, quality=quality)
    if webp is None:
        raise HTTPException(status_code=500, detail="WebP encoding failed.")

    return Response(
        content=webp,
        media_type="image/webp",
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# STATS — quick summary for dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    summary="Violation statistics summary",
    description="Quick stats for dashboard header: total, today, by camera.",
)
async def evidence_stats(
    db: DBService = Depends(get_db_service),
):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")

    daily = await asyncio.to_thread(db.get_daily_stats)
    cameras = await asyncio.to_thread(db.get_camera_summary)

    total_violations = sum(c.get("total_violations", 0) for c in cameras)
    today = daily[0] if daily else {}

    return {
        "total_violations": total_violations,
        "today": {
            "date": today.get("date_vn", ""),
            "count": today.get("total_violations", 0),
        },
        "cameras": [
            {
                "id": c.get("camera_id"),
                "name": c.get("camera_name"),
                "location": c.get("location"),
                "total_violations": c.get("total_violations", 0),
                "status": c.get("status"),
            }
            for c in cameras
        ],
        "daily_trend": [
            {
                "date": d.get("date_vn"),
                "count": d.get("total_violations", 0),
            }
            for d in daily[:30]
        ],
    }
