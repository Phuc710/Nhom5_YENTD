"""Pydantic schema cho camera và provisioning."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class CameraBase(BaseModel):
    camera_id: int
    camera_name: Optional[str] = None
    location: Optional[str] = "Chưa cấu hình"
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
    configured_camera_name: Optional[str] = None
    configured_stream_url: Optional[str] = None
    device_name: Optional[str] = None
    project_name: Optional[str] = None
    device_model: Optional[str] = None
    wifi_ssid: Optional[str] = None
    resolution: Optional[str] = None
    stream_scheme: Optional[str] = None
    stream_host: Optional[str] = None
    stream_port: Optional[int] = None
    stream_path: Optional[str] = None
    stream_snapshot_path: Optional[str] = None
    ip_address: Optional[str] = None
    fw_version: Optional[str] = None
    idf_version: Optional[str] = None
    mac_address: Optional[str] = None
    reset_reason: Optional[str] = None
    capture_interval_ms: Optional[int] = None
    jpeg_quality: Optional[int] = None
    telemetry_interval_ms: Optional[int] = None
    tl_red_ms: Optional[int] = None
    tl_yellow_ms: Optional[int] = None
    tl_green_ms: Optional[int] = None
    target_fw_version: Optional[str] = None
    ota_url: Optional[str] = None
    cpu_temp: Optional[float] = None
    free_heap: Optional[int] = None
    min_free_heap: Optional[int] = None
    wifi_rssi: Optional[int] = None
    uptime_s: Optional[int] = None
    device_state: Optional[str] = None
    light_mode: Optional[str] = None
    wifi_disconnect_count: Optional[int] = None
    extra_attributes: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[datetime] = None
    last_boot_at: Optional[datetime] = None
    online: Optional[bool] = False
    violations_today: Optional[int] = 0
    violations_total: Optional[int] = 0

    class Config:
        from_attributes = True


class ProvisionSync(BaseModel):
    """Payload ESP32 gửi về backend sau provisioning hoặc đồng bộ định danh."""

    camera_id: Optional[int] = None
    camera_name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tb_device_id: Optional[str] = None
    tb_device_name: Optional[str] = None
    device_name: Optional[str] = None
    project_name: Optional[str] = None
    device_model: Optional[str] = None
    wifi_ssid: Optional[str] = None
    resolution: Optional[str] = None
    access_token: Optional[str] = None
    mac_address: Optional[str] = None
    reset_reason: Optional[str] = None
    fw_version: Optional[str] = None
    idf_version: Optional[str] = None
    stream_scheme: Optional[str] = None
    stream_host: Optional[str] = None
    stream_port: Optional[int] = None
    stream_path: Optional[str] = None
    stream_snapshot_path: Optional[str] = None
    stream_url: Optional[str] = None
    ip_address: Optional[str] = None
    last_boot_at: Optional[datetime] = None


class CameraHeartbeat(BaseModel):
    """Payload nhịp sống từ ESP32, chỉ cập nhật runtime cho camera đã tồn tại."""

    camera_id: Optional[int] = None
    tb_device_id: Optional[str] = None
    tb_device_name: Optional[str] = None
    device_name: Optional[str] = None
    mac_address: Optional[str] = None
    fw_version: Optional[str] = None
    idf_version: Optional[str] = None
    ip_address: Optional[str] = None
    stream_scheme: Optional[str] = None
    stream_host: Optional[str] = None
    stream_port: Optional[int] = None
    stream_path: Optional[str] = None
    stream_snapshot_path: Optional[str] = None
    stream_url: Optional[str] = None
    device_state: Optional[str] = None
    online: Optional[bool] = True
    last_boot_at: Optional[datetime] = None


class OtaRequest(BaseModel):
    url: str


class TrafficLightRequest(BaseModel):
    state: str
