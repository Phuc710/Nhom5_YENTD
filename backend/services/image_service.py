"""Lưu 2 ảnh bằng chứng vi phạm: xe (vehicle) và biển số (plate)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ImageService:
    def __init__(self) -> None:
        from backend.config.settings import get_settings

        settings = get_settings()
        self._settings = settings
        self._upload_dir = settings.upload_dir
        self._violations_dir = os.path.join(self._upload_dir, "violations")
        self._plates_dir = os.path.join(self._upload_dir, "plates")
        os.makedirs(self._violations_dir, exist_ok=True)
        os.makedirs(self._plates_dir, exist_ok=True)

    def _unique_name(self, prefix: str, camera_id: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        random_suffix = str(uuid.uuid4())[:6]
        return f"{prefix}_cam{camera_id}_{timestamp}_{random_suffix}.jpg"

    def _build_public_url(self, folder: str, filename: str) -> str:
        rel_path = f"/uploads/{folder}/{filename}"
        if self._settings.public_api_url:
            return self._settings.public_api_url.rstrip("/") + rel_path
        return rel_path

    @staticmethod
    def _write_bytes(filepath: str, image_bytes: bytes) -> None:
        with open(filepath, "wb") as file_obj:
            file_obj.write(image_bytes)

    @staticmethod
    def _write_array(filepath: str, image: np.ndarray) -> None:
        cv2.imwrite(filepath, image)

    async def save_vehicle_image(self, vehicle_image: np.ndarray, camera_id: int) -> Optional[str]:
        if vehicle_image is None or vehicle_image.size == 0:
            return None
        filename = self._unique_name("vehicle", camera_id)
        filepath = os.path.join(self._violations_dir, filename)
        self._write_array(filepath, vehicle_image)
        return self._build_public_url("violations", filename)

    async def save_plate_image(self, plate_image: np.ndarray, camera_id: int) -> Optional[str]:
        if plate_image is None or plate_image.size == 0:
            return None
        filename = self._unique_name("plate", camera_id)
        filepath = os.path.join(self._plates_dir, filename)
        self._write_array(filepath, plate_image)
        return self._build_public_url("plates", filename)

    async def save_frame_bytes(self, image_bytes: bytes, camera_id: int) -> Optional[str]:
        if not image_bytes:
            return None
        filename = self._unique_name("frame", camera_id)
        filepath = os.path.join(self._violations_dir, filename)
        self._write_bytes(filepath, image_bytes)
        return self._build_public_url("violations", filename)

    def delete_image(self, image_path: str) -> bool:
        try:
            candidate = image_path or ""
            if candidate.startswith("/uploads/"):
                rel_path = candidate.replace("/uploads/", "", 1).replace("/", os.sep)
                candidate = os.path.join(self._upload_dir, rel_path)
            if os.path.exists(candidate):
                os.remove(candidate)
                return True
        except Exception as exc:
            logger.error("Xóa ảnh thất bại: %s", exc)
        return False
