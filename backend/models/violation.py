"""Pydantic schema cho vi phạm giao thông."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ViolationBase(BaseModel):
    camera_id: int
    license_plate: Optional[str] = None
    confidence: Optional[float] = None
    full_image_url: str
    cropped_plate_url: Optional[str] = None
    violation_type: str = "red_light"
    traffic_light_state: str = "red"
    timestamp: datetime
    vote_count: Optional[int] = None
    vote_percent: Optional[float] = None
    total_frames: Optional[int] = None
    track_id: Optional[int] = None
    image_quality_score: Optional[float] = None
    bbox_x: Optional[int] = None
    bbox_y: Optional[int] = None
    bbox_w: Optional[int] = None
    bbox_h: Optional[int] = None
    processing_time_ms: Optional[int] = None


class ViolationResponse(ViolationBase):
    id: int
    processed: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    camera_name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    timestamp_vn: Optional[datetime] = None

    class Config:
        from_attributes = True
