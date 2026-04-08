"""
Detection zone routes: CRUD for camera detection zones.
All DB calls run on thread pool via asyncio.to_thread() — non-blocking.
"""
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from api.models import ZoneCreateRequest, ZoneUpdateRequest, MessageResponse
from api.services.db_service import DBService
from api.dependencies import get_db_service

router = APIRouter(prefix="/zones", tags=["Detection Zones"])


def _require_db(db: DBService):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")


@router.get("", summary="List detection zones")
async def list_zones(
    camera_id: Optional[int] = Query(default=None),
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    return await asyncio.to_thread(db.list_zones, camera_id=camera_id)


@router.post("", response_model=MessageResponse, summary="Create a detection zone", status_code=201)
async def create_zone(
    request: ZoneCreateRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    result = await asyncio.to_thread(db.create_zone, request.model_dump())
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to create zone.")
    return MessageResponse(message=f"Zone '{request.zone_name}' created for camera {request.camera_id}.")


@router.put("/{zone_id}", response_model=MessageResponse, summary="Update a detection zone")
async def update_zone(
    zone_id: str,
    request: ZoneUpdateRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return MessageResponse(message="No changes provided.")
    result = await asyncio.to_thread(db.update_zone, zone_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found.")
    return MessageResponse(message=f"Zone {zone_id} updated.")


@router.delete("/{zone_id}", response_model=MessageResponse, summary="Delete a detection zone")
async def delete_zone(
    zone_id: str,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    ok = await asyncio.to_thread(db.delete_zone, zone_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found.")
    return MessageResponse(message=f"Zone {zone_id} deleted.")
