"""
System settings routes: CRUD for system_settings table.
All DB calls run on thread pool via asyncio.to_thread() — non-blocking.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException

from api.models import SettingUpdateRequest, MessageResponse
from api.services.db_service import DBService
from api.dependencies import get_db_service

router = APIRouter(prefix="/settings", tags=["System Settings"])


def _require_db(db: DBService):
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected.")


@router.get("", summary="List all system settings")
async def list_settings(db: DBService = Depends(get_db_service)):
    _require_db(db)
    return await asyncio.to_thread(db.list_settings)


@router.get("/{key}", summary="Get a specific setting")
async def get_setting(key: str, db: DBService = Depends(get_db_service)):
    _require_db(db)
    setting = await asyncio.to_thread(db.get_setting, key)
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found.")
    return setting


@router.put("/{key}", response_model=MessageResponse, summary="Update a system setting")
async def update_setting(
    key: str,
    request: SettingUpdateRequest,
    db: DBService = Depends(get_db_service),
):
    _require_db(db)
    result = await asyncio.to_thread(db.upsert_setting, key, request.value, request.description or "")
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to update setting.")
    return MessageResponse(message=f"Setting '{key}' updated.")
