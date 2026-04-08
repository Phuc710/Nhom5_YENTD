"""Lưu và upload ảnh bằng chứng vi phạm.

Luồng hoạt động:
  1. Ghi ảnh ra đĩa local ngay lập tức (không block AI pipeline).
  2. Tạo background task async để upload lên Supabase Storage.
  3. Sau khi upload thành công → cập nhật URL trong bảng violations.

Cấu trúc thư mục trong bucket Supabase:
  Camera AI/
  ├── violations/   ← ảnh toàn cảnh + ảnh xe (vehicle)
  └── plates/       ← ảnh crop biển số
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class SupabaseStorageUploader:
    """Đóng gói toàn bộ logic upload lên Supabase Storage."""

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket

    def _get_storage(self):
        from backend.database.supabase_client import get_supabase_write
        return get_supabase_write().storage.from_(self._bucket)

    def upload_bytes(self, storage_path: str, image_bytes: bytes) -> Optional[str]:
        """Upload bytes lên Supabase Storage, trả về public URL.

        Args:
            storage_path: Đường dẫn trong bucket, ví dụ "violations/vehicle_cam1_xxx.jpg"
            image_bytes:  Nội dung ảnh JPEG.

        Returns:
            Public URL của ảnh trên Supabase CDN, hoặc None nếu thất bại.
        """
        try:
            storage = self._get_storage()
            storage.upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
            public_url: str = storage.get_public_url(storage_path)
            return public_url
        except Exception as exc:
            logger.warning(
                "⚠️ Upload Supabase Storage thất bại | đường_dẫn=%s | lỗi=%s",
                storage_path, exc,
            )
            return None


class ImageService:
    """Lưu ảnh bằng chứng vi phạm: local trước, Supabase Storage sau."""

    def __init__(self) -> None:
        from backend.config.settings import get_settings

        settings = get_settings()
        self._settings = settings
        self._upload_dir = settings.upload_dir
        self._violations_dir = os.path.join(self._upload_dir, "violations")
        self._plates_dir = os.path.join(self._upload_dir, "plates")
        self._upload_enabled = settings.storage_upload_enabled
        self._uploader = SupabaseStorageUploader(settings.supabase_storage_bucket)

        os.makedirs(self._violations_dir, exist_ok=True)
        os.makedirs(self._plates_dir, exist_ok=True)

    # ──────────────────────────── helpers ────────────────────────────

    def _unique_name(self, prefix: str, camera_id: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        uid = str(uuid.uuid4())[:6]
        return f"{prefix}_cam{camera_id}_{timestamp}_{uid}.jpg"

    def _build_local_url(self, folder: str, filename: str) -> str:
        """URL local trỏ tới backend (fallback khi chưa upload cloud)."""
        rel = f"/uploads/{folder}/{filename}"
        if self._settings.public_api_url:
            return self._settings.public_api_url.rstrip("/") + rel
        return rel

    @staticmethod
    def _encode_jpeg(image: np.ndarray, quality: int = 90) -> Optional[bytes]:
        """Chuyển numpy array → JPEG bytes."""
        if image is None or image.size == 0:
            return None
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return bytes(buf) if ok else None

    # ──────────────────────────── upload nền ─────────────────────────

    def _schedule_cloud_upload(
        self,
        image_bytes: bytes,
        storage_path: str,
        violation_field: str,
        local_url: str,
    ) -> None:
        """Tạo asyncio task để upload ảnh lên cloud và cập nhật violations.

        Không block caller — toàn bộ chạy nền sau khi response đã trả về.
        """
        if not self._upload_enabled or not image_bytes:
            return

        async def _do_upload() -> None:
            loop = asyncio.get_running_loop()
            # Chạy upload trong thread riêng để không block event loop
            cdn_url = await loop.run_in_executor(
                None,
                lambda: self._uploader.upload_bytes(storage_path, image_bytes),
            )
            if cdn_url:
                logger.debug(
                    "☁️  Upload thành công | %s → %s",
                    storage_path, cdn_url,
                )
                # Cập nhật URL trong bảng violations (tìm theo local_url)
                await loop.run_in_executor(None, lambda: self._update_violation_url(
                    field=violation_field,
                    old_url=local_url,
                    new_url=cdn_url,
                ))
            else:
                logger.warning(
                    "⚠️ Giữ nguyên local URL do upload cloud thất bại | %s",
                    local_url,
                )

        try:
            asyncio.create_task(_do_upload(), name=f"storage_upload_{storage_path}")
        except RuntimeError:
            # Không có event loop đang chạy (unit test, v.v.)
            pass

    def _update_violation_url(self, field: str, old_url: str, new_url: str) -> None:
        """Cập nhật 1 trường URL trong bảng violations."""
        try:
            from backend.database.supabase_client import get_supabase_write
            db = get_supabase_write()
            db.table("violations").update({field: new_url}).eq(field, old_url).execute()
        except Exception as exc:
            logger.warning(
                "⚠️ Không cập nhật được URL violations | field=%s | lỗi=%s",
                field, exc,
            )

    # ──────────────────────────── public API ─────────────────────────

    async def save_vehicle_image(self, vehicle_image: np.ndarray, camera_id: int) -> Optional[str]:
        """Lưu ảnh crop xe — local trước, upload Supabase nền sau."""
        image_bytes = self._encode_jpeg(vehicle_image)
        if not image_bytes:
            return None

        filename = self._unique_name("vehicle", camera_id)
        filepath = os.path.join(self._violations_dir, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        local_url = self._build_local_url("violations", filename)
        storage_path = f"violations/{filename}"
        self._schedule_cloud_upload(image_bytes, storage_path, "cropped_vehicle_url", local_url)
        return local_url

    async def save_plate_image(self, plate_image: np.ndarray, camera_id: int) -> Optional[str]:
        """Lưu ảnh crop biển số — local trước, upload Supabase nền sau."""
        image_bytes = self._encode_jpeg(plate_image, quality=95)
        if not image_bytes:
            return None

        filename = self._unique_name("plate", camera_id)
        filepath = os.path.join(self._plates_dir, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        local_url = self._build_local_url("plates", filename)
        storage_path = f"plates/{filename}"
        self._schedule_cloud_upload(image_bytes, storage_path, "cropped_plate_url", local_url)
        return local_url

    async def save_full_image(self, image: np.ndarray, camera_id: int) -> Optional[str]:
        """Lưu ảnh toàn cảnh (scene snapshot) — local trước, upload Supabase nền sau."""
        image_bytes = self._encode_jpeg(image, quality=85)
        if not image_bytes:
            return None

        filename = self._unique_name("scene", camera_id)
        filepath = os.path.join(self._violations_dir, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        local_url = self._build_local_url("violations", filename)
        storage_path = f"violations/{filename}"
        self._schedule_cloud_upload(image_bytes, storage_path, "full_image_url", local_url)
        return local_url

    async def save_frame_bytes(self, image_bytes: bytes, camera_id: int) -> Optional[str]:
        """Lưu ảnh dưới dạng raw bytes (dùng khi đã có JPEG bytes sẵn)."""
        if not image_bytes:
            return None

        filename = self._unique_name("frame", camera_id)
        filepath = os.path.join(self._violations_dir, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        local_url = self._build_local_url("violations", filename)
        storage_path = f"violations/{filename}"
        self._schedule_cloud_upload(image_bytes, storage_path, "full_image_url", local_url)
        return local_url

    def delete_image(self, image_path: str) -> bool:
        """Xóa ảnh local (ảnh cloud được giữ lại cho mục đích lưu trữ)."""
        try:
            candidate = image_path or ""
            if candidate.startswith("/uploads/"):
                rel_path = candidate.replace("/uploads/", "", 1).replace("/", os.sep)
                candidate = os.path.join(self._upload_dir, rel_path)
            if os.path.exists(candidate):
                os.remove(candidate)
                return True
        except Exception as exc:
            logger.error("❌ Xóa ảnh local thất bại: %s", exc)
        return False
