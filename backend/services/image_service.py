"""Lưu ảnh gốc và ảnh biển số đã crop."""

import os
import uuid
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


class ImageService:
    def __init__(self):
        from config.settings import get_settings

        settings = get_settings()
        self._upload_dir = settings.upload_dir
        self._original_dir = os.path.join(self._upload_dir, "original")
        self._plates_dir = os.path.join(self._upload_dir, "detected_plates")
        os.makedirs(self._original_dir, exist_ok=True)
        os.makedirs(self._plates_dir, exist_ok=True)

    def _unique_name(self, prefix: str, camera_id: int) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        random_suffix = str(uuid.uuid4())[:6]
        return f"{prefix}_cam{camera_id}_{timestamp}_{random_suffix}.jpg"

    async def save_image(self, image_bytes: bytes, camera_id: int, image_type: str = "original") -> str:
        """Lưu bytes JPEG ra đĩa và trả về đường dẫn tuyệt đối."""
        filename = self._unique_name("frame", camera_id)
        directory = self._original_dir if image_type == "original" else self._plates_dir
        filepath = os.path.join(directory, filename)
        with open(filepath, "wb") as file_obj:
            file_obj.write(image_bytes)
        return filepath

    async def save_plate_image(self, plate_image: np.ndarray, camera_id: int) -> Optional[str]:
        """Lưu ảnh crop biển số ra đĩa và trả về đường dẫn tuyệt đối."""
        if plate_image is None or plate_image.size == 0:
            return None
        filename = self._unique_name("plate", camera_id)
        filepath = os.path.join(self._plates_dir, filename)
        cv2.imwrite(filepath, plate_image)
        return filepath

    def delete_image(self, image_path: str) -> bool:
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                return True
        except Exception as exc:
            logger.error("Xóa ảnh thất bại: %s", exc)
        return False
