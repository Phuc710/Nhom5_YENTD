"""
models/zone.py — Pydantic schemas Detection Zone
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class ZoneBase(BaseModel):
    zone_name: str = "zone-1"
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    width: int = Field(..., ge=1)
    height: int = Field(..., ge=1)
    zone_type: str = "detection"  # detection | stop_line | roi
    active: bool = True


class ZoneCreate(ZoneBase):
    camera_id: int


class ZoneResponse(ZoneBase):
    id: str
    camera_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ZonesBulkUpdate(BaseModel):
    """Gửi toàn bộ zones của 1 camera (replace all)"""
    zones: List[ZoneBase]
