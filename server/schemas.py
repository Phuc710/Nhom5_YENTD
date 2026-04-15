from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool = True
    token: str
    role: str = "operator"


class CameraBase(BaseModel):
    camera_name: str
    stream_url: str = ""
    location_name: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    install_position: Optional[str] = None
    status: str = "offline"
    last_seen: Optional[str] = None
    device_model: Optional[str] = None
    ip_address: Optional[str] = None
    is_active: int = 1


class CameraCreate(CameraBase):
    camera_code: Optional[str] = None
    camera_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_camera_code(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        code = values.get("camera_code") or values.get("camera_id")
        if code:
            values["camera_code"] = str(code).strip()
        return values


class CameraUpdate(BaseModel):
    camera_name: Optional[str] = None
    stream_url: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    install_position: Optional[str] = None
    status: Optional[str] = None
    last_seen: Optional[str] = None
    device_model: Optional[str] = None
    ip_address: Optional[str] = None
    is_active: Optional[int] = None


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_code: str
    camera_name: str
    stream_url: str
    location_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    install_position: Optional[str] = None
    status: str
    last_seen: Optional[str] = None
    device_model: Optional[str] = None
    ip_address: Optional[str] = None
    is_active: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ViolationBase(BaseModel):
    violation_code: Optional[str] = None
    camera_id: Optional[int] = None
    camera_code: Optional[str] = None
    plate_number: Optional[str] = None
    normalized_plate_number: Optional[str] = None
    violation_type: str = "red_light_crossing"
    violation_time: Optional[str] = None
    location_snapshot: Optional[str] = None
    full_image_url: Optional[str] = None
    vehicle_crop_url: Optional[str] = None
    plate_crop_url: Optional[str] = None
    stop_line_snapshot_url: Optional[str] = None
    light_state: Optional[str] = "RED"
    ocr_text_raw: Optional[str] = None
    ocr_confidence: Optional[float] = None
    vehicle_type: Optional[str] = None
    status: str = "new"


class ViolationCreate(ViolationBase):
    pass


class ViolationOut(ViolationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[str] = None


class DeviceHeartbeatIn(BaseModel):
    camera_code: Optional[str] = None
    camera_id: Optional[int | str] = None
    status: str = Field(default="online")
    latency_ms: Optional[int] = None
    temperature: Optional[float] = None
    signal_strength: Optional[int] = None
    ip_address: Optional[str] = None
    last_seen: Optional[str] = None
    payload: Optional[dict | str] = None

    @model_validator(mode="after")
    def validate_camera_ref(self) -> "DeviceHeartbeatIn":
        if not self.camera_code and self.camera_id is None:
            raise ValueError("camera_code or camera_id is required")
        return self


class DeviceStatusOut(BaseModel):
    camera_id: str
    device_id: str
    device_name: str
    device_type: str
    status: str
    last_seen: Optional[int] = None
    last_seen_str: Optional[str] = None
    last_heartbeat_ts: Optional[int] = None
    signal: Optional[int] = None
    signal_strength: Optional[int] = None
    temp: Optional[float] = None
    latency_ms: Optional[int] = None
    ip_address: Optional[str] = None


class CameraStatusOut(BaseModel):
    camera_id: str
    online: bool
    status: str
    last_seen: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_violation_id: Optional[int] = None
