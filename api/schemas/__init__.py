"""schemas/__init__.py — expose all schemas for easy import."""
from api.schemas.evidence import (
    EvidenceImages,
    ImageVariant,
    BBoxPixel,
    VehicleInfo,
    PlateInfo,
    CameraRef,
    ViolationEvidenceResponse,
    ViolationListItem,
    ViolationListResponse,
    EvidenceUploadResponse,
)

__all__ = [
    "EvidenceImages",
    "ImageVariant",
    "BBoxPixel",
    "VehicleInfo",
    "PlateInfo",
    "CameraRef",
    "ViolationEvidenceResponse",
    "ViolationListItem",
    "ViolationListResponse",
    "EvidenceUploadResponse",
]
