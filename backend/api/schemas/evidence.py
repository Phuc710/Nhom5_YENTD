"""
Evidence schemas — chuẩn hóa response cho web + mobile.

Mọi client (web dashboard, mobile app, third-party) đều nhận
cùng một cấu trúc JSON. Không bao giờ trả raw dict.

Image types:
  original   — Full frame, NO overlay. Dùng làm bằng chứng gốc.
  vehicle    — Crop xe + bbox đỏ + label biển số. Dùng để xem.
  plate      — Crop biển số, phóng to, viền vàng. Dùng để đọc.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class BBoxPixel(BaseModel):
    """Bounding box in pixel coordinates (absolute)."""
    x1: int
    y1: int
    x2: int
    y2: int
    width: int
    height: int


class ImageVariant(BaseModel):
    """A single image asset with URL + metadata."""
    url: str = Field(..., description="Public URL (Supabase Storage or local path)")
    format: str = Field(default="webp", description="Image format: webp, jpeg, png")
    width: Optional[int] = Field(default=None, description="Pixel width")
    height: Optional[int] = Field(default=None, description="Pixel height")
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes")


# ---------------------------------------------------------------------------
# Evidence Images — the 3 types
# ---------------------------------------------------------------------------

class EvidenceImages(BaseModel):
    """
    Complete evidence image set for a violation.

    Three images — all WebP for fast loading:
      original  : Full frame with NO drawings. Raw evidence.
      vehicle   : Cropped vehicle with red bounding box + plate text overlay.
      plate     : Cropped license plate, enlarged, yellow border.

    Usage:
      - Web: show all 3 in a gallery/modal
      - Mobile: show vehicle as thumbnail, plate as badge
      - Legal: use original as official evidence
    """
    original: Optional[ImageVariant] = Field(
        default=None,
        description="Full frame, NO overlay. Legal evidence image.",
    )
    vehicle: Optional[ImageVariant] = Field(
        default=None,
        description="Vehicle crop with red bbox + plate text drawn on top.",
    )
    plate: Optional[ImageVariant] = Field(
        default=None,
        description="License plate crop, enlarged, yellow border for readability.",
    )

    @classmethod
    def from_urls(
        cls,
        full_url: Optional[str],
        vehicle_url: Optional[str],
        plate_url: Optional[str],
    ) -> "EvidenceImages":
        """Build from pre-known URLs (e.g. fetched from DB)."""
        return cls(
            original=ImageVariant(url=full_url) if full_url else None,
            vehicle=ImageVariant(url=vehicle_url) if vehicle_url else None,
            plate=ImageVariant(url=plate_url) if plate_url else None,
        )


# ---------------------------------------------------------------------------
# Full Violation Evidence response
# ---------------------------------------------------------------------------

class VehicleInfo(BaseModel):
    """Detected vehicle metadata."""
    type: Optional[str] = Field(default=None, description="Vehicle type: car, motorbike, truck, bus")
    track_id: Optional[int] = Field(default=None, description="Tracker ID in the video stream")
    bbox: Optional[BBoxPixel] = Field(default=None, description="Bounding box in original frame")


class PlateInfo(BaseModel):
    """License plate OCR result."""
    text: Optional[str] = Field(default=None, description="Recognized plate text e.g. MP04CF0655")
    confidence: Optional[float] = Field(default=None, description="OCR confidence 0.0-1.0")
    vote_count: Optional[int] = Field(default=None, description="Number of frames used for voting")
    vote_percent: Optional[float] = Field(default=None, description="Vote agreement percentage")


class CameraRef(BaseModel):
    """Minimal camera reference (avoid exposing full config)."""
    id: int
    name: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)


class ViolationEvidenceResponse(BaseModel):
    """
    Complete violation evidence — 1 call, everything needed.

    Designed for:
      - Web dashboard violation detail page
      - Mobile app violation detail screen
      - Third-party integration (police system, etc.)

    Response is SELF-CONTAINED — client doesn't need extra calls.
    """
    id: int = Field(..., description="Violation database ID")
    timestamp: str = Field(..., description="Violation time (UTC ISO 8601)")
    timestamp_vn: Optional[str] = Field(default=None, description="Display time (Asia/Ho_Chi_Minh)")

    violation_type: str = Field(..., description="Type: red_light, speeding, wrong_lane, ...")
    traffic_light_state: str = Field(..., description="Light state at violation: red, yellow, green")

    camera: CameraRef = Field(..., description="Camera that caught the violation")
    vehicle: VehicleInfo = Field(default_factory=VehicleInfo, description="Detected vehicle info")
    plate: PlateInfo = Field(default_factory=PlateInfo, description="License plate OCR result")

    images: EvidenceImages = Field(..., description="Evidence images: original, vehicle, plate")

    # Processing metadata
    processing_time_ms: Optional[int] = Field(default=None)
    image_quality_score: Optional[float] = Field(default=None)


class ViolationListItem(BaseModel):
    """
    Compact violation for list/feed views (web + mobile).
    Only what's needed to render a card — NO heavy data.
    """
    id: int
    timestamp: str
    timestamp_vn: Optional[str] = None
    violation_type: str
    traffic_light_state: str
    license_plate: Optional[str] = None
    confidence: Optional[float] = None

    # Thumbnail only — use /violations/{id}/evidence for full images
    thumbnail_url: Optional[str] = Field(
        default=None,
        description="Vehicle crop URL for list thumbnail. Null if not yet available.",
    )

    camera_id: int
    camera_name: Optional[str] = None
    camera_location: Optional[str] = None


class ViolationListResponse(BaseModel):
    """Paginated list of violations."""
    items: List[ViolationListItem]
    total: int
    limit: int
    offset: int
    has_more: bool


# ---------------------------------------------------------------------------
# Upload response
# ---------------------------------------------------------------------------

class EvidenceUploadResponse(BaseModel):
    """Response after uploading violation images."""
    violation_id: int
    message: str = "Violation recorded."
    images: EvidenceImages
