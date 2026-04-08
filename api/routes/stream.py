"""
Streaming routes: start/stop video capture and serve MJPEG feed.
Blocking cv2 operations run on thread pool — non-blocking.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.models import StreamStartRequest, StreamStatusResponse, MessageResponse
from api.services.stream_manager import StreamManager
from api.dependencies import get_stream_manager

router = APIRouter(prefix="/stream", tags=["Streaming"])


@router.post(
    "/start",
    response_model=MessageResponse,
    summary="Start video stream",
    description=(
        "Start capturing from a video source.\n\n"
        "**source** examples:\n"
        "- `\"0\"` — webcam device 0\n"
        "- `\"rtsp://user:pass@192.168.1.100:554/stream\"` — RTSP IP camera\n"
        "- `\"http://192.168.4.1:81/stream\"` — ESP32-S3 MJPEG stream\n"
        "- `\"path/to/video.mp4\"` — local video file\n"
    ),
)
async def stream_start(
    request: StreamStartRequest,
    manager: StreamManager = Depends(get_stream_manager),
):
    ok = await asyncio.to_thread(manager.start, request.source, request.mode)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Could not open video source: {request.source}. "
                   "Check the URL/device ID and ensure the source is available.",
        )
    return MessageResponse(message=f"Stream started from: {request.source}")


@router.post(
    "/stop",
    response_model=MessageResponse,
    summary="Stop video stream",
)
async def stream_stop(
    manager: StreamManager = Depends(get_stream_manager),
):
    if not manager.is_active:
        return MessageResponse(message="No active stream to stop.")
    await asyncio.to_thread(manager.stop)
    return MessageResponse(message="Stream stopped.")


@router.get(
    "/status",
    response_model=StreamStatusResponse,
    summary="Stream status",
)
async def stream_status(
    manager: StreamManager = Depends(get_stream_manager),
):
    status = manager.get_status()
    return StreamStatusResponse(**status)


@router.get(
    "/feed",
    summary="MJPEG video feed",
    description=(
        "Live MJPEG video stream with detection overlays.\n\n"
        "Embed in HTML: `<img src=\"http://host:port/stream/feed\" />`\n\n"
        "**Note:** A stream must be started first via `POST /stream/start`."
    ),
)
async def stream_feed(
    manager: StreamManager = Depends(get_stream_manager),
):
    if not manager.is_active:
        raise HTTPException(status_code=409, detail="No active stream. Start one via POST /stream/start.")
    return StreamingResponse(
        manager.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
