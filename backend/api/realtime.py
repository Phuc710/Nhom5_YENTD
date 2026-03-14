"""Realtime endpoints for frontend SSE subscriptions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.services.realtime_service import realtime_service

router = APIRouter(prefix="/realtime", tags=["Realtime"])


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
