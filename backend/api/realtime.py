"""Realtime endpoints for frontend SSE subscriptions."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.services.realtime_service import realtime_service

router = APIRouter(prefix="/realtime", tags=["Realtime"])


@router.get("/status")
async def realtime_status():
    """
    Ping endpoint nhẹ để Frontend kiểm tra backend có sống không.
    Web dùng endpoint này với logic retry 5 lần trước khi mở SSE.
    Không cần auth, không block, trả về ngay < 5ms.
    """
    return JSONResponse({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    })


@router.get("/stream")
async def stream_realtime_events(request: Request) -> StreamingResponse:
    queue = await realtime_service.subscribe()

    async def event_stream():
        try:
            yield realtime_service.encode(
                "ready",
                {"type": "connection.ready", "resources": [], "timestamp": None},
            )

            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield realtime_service.encode("update", message)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            realtime_service.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

