"""
Camera routes: CRUD for cameras and provisioning.
All DB calls run on thread pool via asyncio.to_thread() — non-blocking.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    CameraCreateRequest,
    CameraUpdateRequest,
    ProvisioningRequest,
    MessageResponse,
)
from api.services.db_service import DBService
from api.dependencies import get_db_service

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def _require_db(db: DBService):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")


@router.get("", summary="List all cameras")
async def list_cameras(
    summary: bool = False,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    if summary:
        return await asyncio.to_thread(db.get_camera_summary)
    return await asyncio.to_thread(db.list_cameras)


@router.get("/{camera_id}", summary="Get camera detail")
async def get_camera(
    camera_id: int,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    camera = await asyncio.to_thread(db.get_camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found.")
    return camera


@router.post("", response_model=MessageResponse, summary="Create a camera", status_code=201)
async def create_camera(
    request: CameraCreateRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    result = await asyncio.to_thread(db.create_camera, request.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to create camera.")
    return MessageResponse(message=f"Camera {request.camera_id} created successfully.")


@router.put("/{camera_id}", response_model=MessageResponse, summary="Update camera config")
async def update_camera(
    camera_id: int,
    request: CameraUpdateRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return MessageResponse(message="No changes provided.")
    result = await asyncio.to_thread(db.update_camera, camera_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found.")
    return MessageResponse(message=f"Camera {camera_id} updated.")


@router.delete("/{camera_id}", response_model=MessageResponse, summary="Delete a camera")
async def delete_camera(
    camera_id: int,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    ok = await asyncio.to_thread(db.delete_camera, camera_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found.")
    return MessageResponse(message=f"Camera {camera_id} deleted.")


@router.post(
    "/{camera_id}/provision",
    response_model=MessageResponse,
    summary="Provision / update ESP32-S3 identity",
)
async def provision_camera(
    camera_id: int,
    request: ProvisioningRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    data = request.model_dump(exclude_none=True)
    result = await asyncio.to_thread(db.upsert_provisioning, camera_id, data)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to provision camera.")
    return MessageResponse(message=f"Camera {camera_id} provisioning updated.")
