"""
models/camera.py — Pydantic schemas cho Camera + Provisioning
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ---- Camera -----------------------------------------------

class CameraBase(BaseModel):
    camera_id: int
    camera_name: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    description: Optional[str] = None
    tb_device_name: Optional[str] = None
    status: str = "inactive"


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    """Fields có thể cập nhật từ frontend"""
    camera_name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    description: Optional[str] = None
    tb_device_name: Optional[str] = None
    status: Optional[str] = None


class CameraResponse(CameraBase):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Từ view_camera_summary
    ip_address: Optional[str] = None
    fw_version: Optional[str] = None
    mac_address: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    online: Optional[bool] = False
    violations_today: Optional[int] = 0
    violations_total: Optional[int] = 0

    class Config:
        from_attributes = True


# ---- Provisioning -----------------------------------------

class ProvisionSync(BaseModel):
    """Gửi từ backend ESP32 khi provisioning thành công"""
    camera_id: int
    tb_device_id: Optional[str] = None
    access_token: Optional[str] = None
    mac_address: Optional[str] = None
    fw_version: Optional[str] = None
    idf_version: Optional[str] = None
    ip_address: Optional[str] = None


class ProvisionResponse(BaseModel):
    camera_id: int
    tb_device_id: Optional[str] = None
    mac_address: Optional[str] = None
    fw_version: Optional[str] = None
    ip_address: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    online: Optional[bool] = False
    provisioned_at: Optional[datetime] = None
