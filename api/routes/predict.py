"""
Prediction routes: process single images or video frames.

All heavy ALPR processing runs on thread pool via asyncio.to_thread()
to avoid blocking the FastAPI event loop.
"""
import asyncio
import base64
import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from pydantic import BaseModel

from api.models import PredictResponse, MessageResponse
from api.services.alpr_service import ALPRService
from api.dependencies import get_alpr_service

router = APIRouter(prefix="/predict", tags=["Prediction"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_upload(contents: bytes) -> np.ndarray:
    """Decode uploaded file bytes into a BGR numpy array."""
    arr = np.frombuffer(contents, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image. Ensure it is a valid JPEG/PNG.")
    return frame


def _decode_base64(b64_str: str) -> np.ndarray:
    """Decode a base64-encoded image string into a BGR numpy array."""
    try:
        img_bytes = base64.b64decode(b64_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 string.")
    return _decode_upload(img_bytes)


def _ensure_ready(service: ALPRService):
    if not service.is_ready:
        raise HTTPException(status_code=503, detail="Models not loaded yet. Please wait.")


class Base64ImageRequest(BaseModel):
    """JSON body with base64-encoded image."""
    image_base64: str


# ---------------------------------------------------------------------------
# /predict/image — file upload (resets tracker)
# ---------------------------------------------------------------------------

@router.post(
    "/image",
    response_model=PredictResponse,
    summary="Process a single image (file upload)",
    description="Upload an image via multipart form. Tracker is **reset** before processing.",
)
async def predict_image(
    file: UploadFile = File(...),
    service: ALPRService = Depends(get_alpr_service),
):
    _ensure_ready(service)
    contents = await file.read()
    frame = _decode_upload(contents)
    # Run heavy ALPR inference on thread pool — non-blocking
    _, detections, frame_count = await asyncio.to_thread(
        service.process_and_extract, frame, True
    )
    return PredictResponse(detections=detections, frame_count=frame_count)


# ---------------------------------------------------------------------------
# /predict/image/b64 — base64 JSON (resets tracker)
# ---------------------------------------------------------------------------

@router.post(
    "/image/b64",
    response_model=PredictResponse,
    summary="Process a single image (base64 JSON)",
    description="Send a base64-encoded image in the JSON body. Tracker is **reset** before processing.",
)
async def predict_image_b64(
    body: Base64ImageRequest,
    service: ALPRService = Depends(get_alpr_service),
):
    _ensure_ready(service)
    frame = _decode_base64(body.image_base64)
    _, detections, frame_count = await asyncio.to_thread(
        service.process_and_extract, frame, True
    )
    return PredictResponse(detections=detections, frame_count=frame_count)


# ---------------------------------------------------------------------------
# /predict/frame — file upload (keeps tracker)
# ---------------------------------------------------------------------------

@router.post(
    "/frame",
    response_model=PredictResponse,
    summary="Process a video frame (file upload)",
    description="Upload a frame via multipart form. Tracker state is **maintained** across calls.",
)
async def predict_frame(
    file: UploadFile = File(...),
    service: ALPRService = Depends(get_alpr_service),
):
    _ensure_ready(service)
    contents = await file.read()
    frame = _decode_upload(contents)
    _, detections, frame_count = await asyncio.to_thread(
        service.process_and_extract, frame, False
    )
    return PredictResponse(detections=detections, frame_count=frame_count)


# ---------------------------------------------------------------------------
# /predict/frame/b64 — base64 JSON (keeps tracker)
# ---------------------------------------------------------------------------

@router.post(
    "/frame/b64",
    response_model=PredictResponse,
    summary="Process a video frame (base64 JSON)",
    description="Send a base64-encoded frame in the JSON body. Tracker state is **maintained**.",
)
async def predict_frame_b64(
    body: Base64ImageRequest,
    service: ALPRService = Depends(get_alpr_service),
):
    _ensure_ready(service)
    frame = _decode_base64(body.image_base64)
    _, detections, frame_count = await asyncio.to_thread(
        service.process_and_extract, frame, False
    )
    return PredictResponse(detections=detections, frame_count=frame_count)


# ---------------------------------------------------------------------------
# /reset — reset tracker
# ---------------------------------------------------------------------------

reset_router = APIRouter(tags=["Prediction"])


@reset_router.post(
    "/reset",
    response_model=MessageResponse,
    summary="Reset tracker",
    description="Reset the object tracker state and frame counter.",
)
async def reset_tracker(service: ALPRService = Depends(get_alpr_service)):
    await asyncio.to_thread(service.reset)
    return MessageResponse(message="Tracker reset successfully.")
