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
        self._camera_locks: Dict[int, asyncio.Lock] = {}
        self._camera_repo = CameraRepository()

    # ──────────────────────────── Public API ────────────────────────────────

    async def start_all(self) -> None:
        """Khởi động worker cho tất cả camera active có stream_url."""
        report = self.audit_cameras()
        started = 0
        logger.info(
            "📋 [Kiểm tra] Kiểm tra khởi động camera | Total=%s | Ready=%s | Skipped=%s",
            report["total"],
            len(report["ready"]),
            len(report["skipped"]),
        )

        for item in report["ready"]:
            logger.info(
                "✅ [Sẵn sàng] Camera sẵn sàng | Cam: %s | Name: %s | Stream: %s",
                item["camera_id"],
                item["camera_name"],
                item["stream_url"],
            )
            if await self.start_camera(item["camera_id"], item["stream_url"]):
                started += 1

        for item in report["skipped"]:
            logger.warning(
                "🕒 [Đang chờ] Camera chưa đủ điều kiện stream | Cam: %s | Name: %s | Lý do: %s",
                item.get("camera_id") or "N/A",
                item.get("camera_name") or "N/A",
                ", ".join(item["issues"]),
            )

        logger.info("🚀 [Quản lý luồng] Khởi động thành công %s workers", started)

    async def stop_all(self) -> None:
        """Dừng toàn bộ workers — gọi khi app shutdown."""
        cids = list(self._workers.keys())
        for cid in cids:
            await self.stop_camera(cid)
        logger.info("⏹️  StreamManager đã dừng tất cả workers")

    async def start_camera(self, camera_id: int, stream_url: str) -> bool:
        """Khởi động worker cho 1 camera (gọi khi camera được provision/update)."""
        normalized_stream_url = (stream_url or "").strip()
        if not normalized_stream_url:
            return False

        async with self._get_camera_lock(camera_id):
            existing_worker = self._workers.get(camera_id)
            if (
                existing_worker
                and existing_worker.is_running
                and (existing_worker.stream_url or "").strip() == normalized_stream_url
            ):
                return True
            if existing_worker:
                await self._stop_worker(camera_id)
            return await self._start_worker(camera_id, normalized_stream_url)

    async def stop_camera(self, camera_id: int) -> bool:
        """Dừng worker cho 1 camera (gọi khi camera bị xóa)."""
        async with self._get_camera_lock(camera_id):
            return await self._stop_worker(camera_id)

    async def reload_zones(self, camera_id: int) -> bool:
        """Tải lại zones cho worker (gọi khi zones thay đổi từ web UI)."""
        worker = self._workers.get(camera_id)
        if not worker:
            return False
        await worker.reload_zones()
        logger.info("🔄 [Quản lý luồng] Đã reload zones | Cam: %s", camera_id)
        return True

    def status(self, camera_id: Optional[int] = None) -> dict:
        """Trả về trạng thái workers."""
        if camera_id is not None:
            w = self._workers.get(camera_id)
            return w.status() if w else {
                "camera_id":          camera_id,
                "running":            False,
                "connected":          False,
                "stream_url":         None,
                "retry_count":        0,
                "last_error":         None,
                "last_connected_at":  None,
                "last_frame_at":      None,
                "frames_received":    0,
                "frames_ai_processed":0,
            }

        return {
            "total": len(self._workers),
            "workers": [w.status() for _, w in self._workers.items()],
        }

    def audit_cameras(self) -> dict:
        cameras = self._camera_repo.get_all()
        ready = []
        skipped = []

        for camera in cameras:
            item = self._build_camera_audit_item(camera)
            if item["issues"]:
                skipped.append(item)
            else:
                ready.append(item)

        return {
            "total": len(cameras),
            "ready": ready,
            "skipped": skipped,
        }

    # ────────────────────────── Internal ───────────────────────────────────

    async def _start_worker(self, camera_id: int, stream_url: str) -> bool:
        existing_worker = self._workers.get(camera_id)
        if (
            existing_worker
            and existing_worker.is_running
            and (existing_worker.stream_url or "").strip() == stream_url
        ):
            return True
        if existing_worker and not existing_worker.is_running:
            self._workers.pop(camera_id, None)
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

    def _get_camera_lock(self, camera_id: int) -> asyncio.Lock:
        lock = self._camera_locks.get(camera_id)
        if lock is None:
            lock = asyncio.Lock()
            self._camera_locks[camera_id] = lock
        return lock

    def _build_camera_audit_item(self, camera: dict) -> dict:
        camera_id = camera.get("camera_id")
        camera_name = camera.get("camera_name") or camera.get("tb_device_name") or "N/A"
        stream_url = str(camera.get("stream_url") or "").strip()
        status = camera.get("status")
        issues = []

        if camera_id in (None, ""):
            issues.append("missing_camera_id")
        if self._is_placeholder_scalar(camera_name):
            issues.append("placeholder_identity")
        if not stream_url:
            issues.append("missing_stream_url")
        elif not (stream_url.startswith("http://") or stream_url.startswith("https://")):
            issues.append("invalid_stream_url")
        if status not in ("active", None):
            issues.append(f"status={status}")

        return {
            "camera_id": int(camera_id) if camera_id not in (None, "") else None,
            "camera_name": camera_name,
            "stream_url": stream_url,
            "status": status,
            "issues": issues,
        }

    @staticmethod
    def _is_placeholder_scalar(value: object) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in {"", "string", "null", "none", "-", "--", "n/a", "na", "unknown"}


# Singleton instance
stream_manager = StreamManager()
