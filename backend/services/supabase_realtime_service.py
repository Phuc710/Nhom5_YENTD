"""Supabase Realtime listener — lắng nghe DB thay đổi và cập nhật backend cache."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class SupabaseRealtimeService:
    """Lắng nghe thay đổi trên Supabase (Postgres Changes) qua Realtime channel.

    Dùng supabase-py v2 async channel.  Backend sẽ nhận event khi bất kỳ
    row nào trong các bảng được theo dõi bị INSERT / UPDATE / DELETE — dù
    thay đổi đến từ ESP32, Web hay trực tiếp trên Dashboard Supabase.
    """

    def __init__(self) -> None:
        self._on_camera_change_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._channel: Any = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def on_camera_change(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Đăng ký callback được gọi khi bảng cameras hoặc camera_provisioning đổi."""
        self._on_camera_change_callbacks.append(callback)

    def _fire_camera_callbacks(self, payload: Dict[str, Any]) -> None:
        for cb in self._on_camera_change_callbacks:
            try:
                cb(payload)
            except Exception as exc:
                logger.warning("⚠️ Realtime callback lỗi: %s", exc)

    async def start(self) -> None:
        """Kết nối và bắt đầu lắng nghe Supabase Realtime."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop(), name="supabase_realtime")
        logger.info("📡 [DB-REALTIME] Đang kết nối Supabase...")

    async def stop(self) -> None:
        """Dừng listener."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("📡 Supabase Realtime: đã dừng")

    async def _listen_loop(self) -> None:
        """Vòng lặp kết nối lại khi bị ngắt."""
        retry_delay = 5
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "⚠️ Supabase Realtime ngắt kết nối: %s — thử lại sau %ss",
                    exc, retry_delay
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def _connect_and_listen(self) -> None:
        """Tạo channel và subscribe tới postgres_changes."""
        try:
            from supabase._async.client import AsyncClient
            from backend.database.supabase_client import get_supabase_read
            from backend.config.settings import get_settings
            from supabase import acreate_client
        except ImportError as exc:
            raise RuntimeError(f"supabase-py không hỗ trợ async realtime: {exc}")

        settings = get_settings()
        try:
            client: AsyncClient = await acreate_client(settings.supabase_url, settings.supabase_key)
        except Exception as exc:
            raise RuntimeError(f"Không tạo được Supabase async client: {exc}")

        channel = client.channel("db-changes")
        channel.on_postgres_changes(
            event="*",
            schema="public",
            table="cameras",
            callback=self._handle_camera_change,
        )
        channel.on_postgres_changes(
            event="*",
            schema="public",
            table="camera_provisioning",
            callback=self._handle_camera_change,
        )

        # Đăng ký và giữ kết nối
        # supabase-py v2: channel.subscribe() trả về channel object (không phải string)
        try:
            await channel.subscribe()
            # Kiểm tra trạng thái sau khi subscribe
            state = getattr(channel, "state", None) or getattr(channel, "_state", None) or ""
            state_str = str(state).upper()
            if "SUBSCRIBED" in state_str or "JOINED" in state_str or "JOINING" in state_str:
                logger.info("📡 [DB-REALTIME] ✅ Đang lắng nghe bảng cameras & camera_provisioning")
            else:
                logger.info("📡 [DB-REALTIME] ✅ Đã đăng ký (state=%s)", state_str or "ok")
        except Exception as exc:
            logger.error(
                "❌ Lỗi đăng ký Supabase Realtime: %s\n"
                "👉 HƯỠNG DẪN: Hãy chắc chắn đã bật 'Realtime' cho bảng 'cameras' và 'camera_provisioning' trong Dashboard Supabase.",
                exc,
            )
            raise  # Cho phép _listen_loop retry tự động

        self._channel = channel

        # Giữ kết nối sống
        while self._running:
            await asyncio.sleep(30)

    def _handle_camera_change(self, payload: Dict[str, Any]) -> None:
        """Handler sync được gọi bởi supabase-py khi nhận event."""
        table = payload.get("table") or payload.get("schema", "")
        event = payload.get("eventType") or payload.get("type", "")
        logger.debug("📡 Realtime event | table=%s | event=%s", table, event)
        self._fire_camera_callbacks(payload)


supabase_realtime_service = SupabaseRealtimeService()
