"""Pydantic schema cho camera và provisioning."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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
    """Các trường dashboard có thể cập nhật."""

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
    ip_address: Optional[str] = None
    fw_version: Optional[str] = None
    mac_address: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    online: Optional[bool] = False
    violations_today: Optional[int] = 0
    violations_total: Optional[int] = 0

    class Config:
        from_attributes = True


class ProvisionSync(BaseModel):
    """Payload ESP32 gửi về backend sau khi provisioning hoặc MQTT ổn định."""

    camera_id: int
    tb_device_id: Optional[str] = None
    tb_device_name: Optional[str] = None
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
