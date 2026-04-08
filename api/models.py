"""
Pydantic models (schemas) for API request/response serialization.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class BBox(BaseModel):
    """Bounding box in pixel coordinates."""
    x1: float
    y1: float
    x2: float
    y2: float


class Detection(BaseModel):
    """Single detected vehicle with optional license plate."""
    track_id: int
    bbox: BBox
    vehicle_type: str = ""
    license_plate: str = ""
    plate_bbox: Optional[BBox] = None
    confidence: float = 0.0


class PredictResponse(BaseModel):
    """Standard response from /predict/* endpoints."""
    detections: List[Detection] = []
    frame_count: int = 0


class HealthResponse(BaseModel):
    """Response from /health endpoint."""
    status: str = "ok"
    gpu_available: bool = False
    device: str = "cpu"
    vehicle_model_loaded: bool = False
    plate_model_loaded: bool = False
    ocr_enabled: bool = False


class ConfigResponse(BaseModel):
    """Current runtime configuration."""
    vehicle_weight: str
    plate_weight: str
    device: str
    vconf: float
    pconf: float
    ocr_thres: float
    read_plate: bool
    deepsort: bool
    lang: str


class ConfigUpdateRequest(BaseModel):
    """Partial config update (only supplied fields are changed)."""
    vconf: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pconf: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ocr_thres: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    read_plate: Optional[bool] = None
    lang: Optional[str] = None
    device: Optional[str] = None


class ServiceInfoResponse(BaseModel):
    """Response for the root endpoint."""
    service: str = "TrafficCam ALPR API"
    version: str = "1.0.0"
    endpoints: dict = {}


# ---------------------------------------------------------------------------
# Stream schemas
# ---------------------------------------------------------------------------

class StreamStartRequest(BaseModel):
    """Request body to start a video stream."""
    source: str = Field(
        ...,
        description="Video source: integer for webcam, URL for RTSP/MJPEG/HTTP, or file path",
        examples=["0", "rtsp://user:pass@192.168.1.100:554/stream", "http://192.168.4.1:81/stream"],
    )
    mode: str = Field(
        default="lpr",
        description="Processing mode: 'lpr' (license plate recognition) or 'detect' (vehicle detection only)",
    )


class StreamStatusResponse(BaseModel):
    """Current stream status."""
    active: bool = False
    source: str = ""
    mode: str = ""
    fps: float = 0.0
    frame_count: int = 0
    resolution: Optional[dict] = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


# ---------------------------------------------------------------------------
# Database / Camera schemas
# ---------------------------------------------------------------------------

class CameraCreateRequest(BaseModel):
    """Request body to create a camera."""
    camera_id: int
    camera_name: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    description: Optional[str] = None
    tb_device_name: Optional[str] = None
    status: str = "inactive"
    confidence_threshold: float = 0.5
    operation_mode: str = "balanced"
    rotate_180: bool = False
    flip_horizontal: bool = False


class CameraUpdateRequest(BaseModel):
    """Partial camera update."""
    camera_name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    description: Optional[str] = None
    tb_device_name: Optional[str] = None
    status: Optional[str] = None
    confidence_threshold: Optional[float] = None
    operation_mode: Optional[str] = None
    rotate_180: Optional[bool] = None
    flip_horizontal: Optional[bool] = None


class ProvisioningRequest(BaseModel):
    """ESP32-S3 self-provisioning request."""
    tb_device_id: Optional[str] = None
    tb_device_name: Optional[str] = None
    device_name: Optional[str] = None
    project_name: Optional[str] = None
    device_model: Optional[str] = None
    wifi_ssid: Optional[str] = None
    resolution: Optional[str] = None
    access_token: Optional[str] = None
    mac_address: Optional[str] = None
    fw_version: Optional[str] = None
    idf_version: Optional[str] = None
    stream_scheme: str = "http"
    stream_host: Optional[str] = None
    stream_port: int = 81
    stream_path: str = "/stream"
    stream_snapshot_path: str = "/snapshot"
    ip_address: Optional[str] = None
    extra_attributes: Optional[dict] = None


# ---------------------------------------------------------------------------
# Violation schemas
# ---------------------------------------------------------------------------

class ViolationCreateRequest(BaseModel):
    """Record a new traffic violation."""
    camera_id: int
    license_plate: Optional[str] = None
    confidence: Optional[float] = None
    full_image_url: str
    cropped_vehicle_url: Optional[str] = None
    cropped_plate_url: Optional[str] = None
    stop_line_snapshot_url: Optional[str] = None
    violation_type: str = "red_light"
    traffic_light_state: str = "red"
    timestamp: str  # ISO 8601 UTC
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


class OCRResultRequest(BaseModel):
    """Add an OCR voting frame result."""
    violation_id: int
    frame_id: int
    track_id: Optional[int] = None
    license_plate: Optional[str] = None
    confidence: Optional[float] = None
    quality_score: Optional[float] = None


# ---------------------------------------------------------------------------
# Zone schemas
# ---------------------------------------------------------------------------

class ZoneCreateRequest(BaseModel):
    """Create a detection zone."""
    camera_id: int
    zone_name: str = "zone-1"
    x: int = 0
    y: int = 0
    width: int = 100
    height: int = 100
    zone_type: str = "detection"
    active: bool = True


class ZoneUpdateRequest(BaseModel):
    """Update a detection zone."""
    zone_name: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    zone_type: Optional[str] = None
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# MQTT schemas
# ---------------------------------------------------------------------------

class MQTTPublishRequest(BaseModel):
    """Generic MQTT publish."""
    topic: str
    payload: dict
    qos: int = Field(default=1, ge=0, le=2)
    retain: bool = False


class TrafficLightControlRequest(BaseModel):
    """Control a traffic light."""
    state: str = Field(
        ..., description="Traffic light state: red, yellow, green, off, flash_yellow"
    )
    duration_s: Optional[int] = Field(
        default=None, description="Duration in seconds (optional)"
    )


class DisplayControlRequest(BaseModel):
    """Control a 7-segment display."""
    text: str = Field(..., description="Text to display")
    brightness: int = Field(default=7, ge=0, le=15, description="Brightness level 0-15")


class CameraControlRequest(BaseModel):
    """Control an ESP32-S3 camera."""
    command: str = Field(
        ...,
        description="Command: restart, rotate, set_resolution, set_quality, stream_start, stream_stop",
    )
    params: Optional[dict] = Field(default=None, description="Additional parameters")


class MQTTStatusResponse(BaseModel):
    """MQTT connection status."""
    connected: bool = False
    broker: str = ""
    enabled: bool = False
    client_id: str = ""


# ---------------------------------------------------------------------------
# Settings schemas
# ---------------------------------------------------------------------------

class SettingUpdateRequest(BaseModel):
    """Update a system setting."""
    value: dict
    description: Optional[str] = None
