"""Realtime event hub for Server-Sent Events (SSE)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional, Set


class RealtimeService:
    """In-memory event hub for lightweight frontend realtime updates."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queues: Set[asyncio.Queue[Dict[str, Any]]] = set()
        self._lock = Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=32)
        with self._lock:
            self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        with self._lock:
            self._queues.discard(queue)

    def publish(
        self,
        *,
        event_type: str,
        resources: list[str],
        table: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._loop is None:
            return

        message: Dict[str, Any] = {
            "type": event_type,
            "resources": resources,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if table:
            message["table"] = table
        if payload:
            message["payload"] = payload

        self._loop.call_soon_threadsafe(self._broadcast, message)

    def _broadcast(self, message: Dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._queues)

        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue

    @staticmethod
    def encode(event: str, data: Dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"


realtime_service = RealtimeService()
