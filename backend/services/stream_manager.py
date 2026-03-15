"""
StreamManager — quản lý vòng đời tất cả StreamWorker theo camera.

Singleton được khởi động trong lifespan của FastAPI app.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional

from backend.repositories.camera_repository import CameraRepository
from backend.services.stream_worker import StreamWorker
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class StreamManager:
    """
    Quản lý tập trung tất cả StreamWorker.

    Dùng trong main.py:
        await stream_manager.start_all()
        ...
        await stream_manager.stop_all()
    """

    def __init__(self) -> None:
        self._workers: Dict[int, StreamWorker] = {}
        self._camera_repo = CameraRepository()

    # ──────────────────────────── Public API ────────────────────────────────

    async def start_all(self) -> None:
        """Khởi động worker cho tất cả camera active có stream_url."""
        cameras = self._camera_repo.get_all()
        started = 0
        for camera in cameras:
            stream_url = camera.get("stream_url")
            camera_id_raw = camera.get("camera_id")
            if not stream_url or camera_id_raw is None:
                continue
            camera_id = int(camera_id_raw)
            if camera.get("status") not in ("active", None):
                continue
            await self._start_worker(camera_id, stream_url)
            started += 1

        logger.info("🚀 StreamManager khởi động %s workers", started)

    async def stop_all(self) -> None:
        """Dừng toàn bộ workers — gọi khi app shutdown."""
        cids = list(self._workers.keys())
        for cid in cids:
            await self._stop_worker(cid)
        logger.info("⏹️  StreamManager đã dừng tất cả workers")

    async def start_camera(self, camera_id: int, stream_url: str) -> bool:
        """Khởi động worker cho 1 camera (gọi khi camera được provision/update)."""
        if camera_id in self._workers:
            await self._stop_worker(camera_id)
        return await self._start_worker(camera_id, stream_url)

    async def stop_camera(self, camera_id: int) -> bool:
        """Dừng worker cho 1 camera (gọi khi camera bị xóa)."""
        return await self._stop_worker(camera_id)

    async def reload_zones(self, camera_id: int) -> bool:
        """Tải lại zones cho worker (gọi khi zones thay đổi từ web UI)."""
        worker = self._workers.get(camera_id)
        if not worker:
            return False
        await worker.reload_zones()
        logger.info("🔄 Đã reload zones | Cam: %s", camera_id)
        return True

    def status(self, camera_id: Optional[int] = None) -> dict:
        """Trả về trạng thái workers."""
        if camera_id is not None:
            w = self._workers.get(camera_id)
            return {
                "camera_id": camera_id,
                "running": w.is_running if w else False,
                "stream_url": w.stream_url if w else None,
            }
        return {
            "total": len(self._workers),
            "workers": [
                {
                    "camera_id": cid,
                    "running": w.is_running,
                    "stream_url": w.stream_url,
                }
                for cid, w in self._workers.items()
            ],
        }

    # ────────────────────────── Internal ───────────────────────────────────

    async def _start_worker(self, camera_id: int, stream_url: str) -> bool:
        try:
            worker = StreamWorker(camera_id, stream_url)
            self._workers[camera_id] = worker
            worker.start()
            return True
        except Exception as exc:
            logger.error("❌ Không thể khởi động worker cam=%s: %s", camera_id, exc)
            return False

    async def _stop_worker(self, camera_id: int) -> bool:
        worker = self._workers.pop(camera_id, None)
        if worker:
            await worker.stop()
            return True
        return False


# Singleton instance
stream_manager = StreamManager()
