"""Nghiệp vụ tạo và truy vấn vi phạm."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from database.models import TrafficLightState, ViolationType
from database.supabase_client import get_supabase
from utils.logger import get_logger

logger = get_logger(__name__)


class ViolationService:
    """Tạo và quản lý vi phạm, bao gồm kiểm tra trùng lặp."""

    def __init__(self):
        from config.settings import get_settings

        settings = get_settings()
        self._dedup_window = settings.dedup_time_window
        self._db = get_supabase()

    async def create_violation(
        self,
        camera_id: int,
        image_url: str,
        plate_image_url: Optional[str],
        license_plate: Optional[str],
        confidence: Optional[float],
        traffic_light_state: TrafficLightState,
        timestamp: datetime,
        vote_count: Optional[int] = None,
        vote_percent: Optional[float] = None,
        total_frames: Optional[int] = None,
        track_id: Optional[int] = None,
        image_quality_score: Optional[float] = None,
        processing_time_ms: Optional[int] = None,
        bbox_x: Optional[int] = None,
        bbox_y: Optional[int] = None,
        bbox_w: Optional[int] = None,
        bbox_h: Optional[int] = None,
    ) -> Dict:
        """Tạo vi phạm mới, bỏ qua nếu trùng trong khoảng thời gian dedup."""
        if license_plate and await self._is_duplicate(camera_id, license_plate, timestamp):
            logger.warning(
                "Bỏ qua vi phạm trùng lặp biển=%s camera=%s",
                license_plate,
                camera_id,
            )
            return {"success": False, "message": "duplicate", "license_plate": license_plate}

        data = {
            "camera_id": camera_id,
            "full_image_url": image_url,
            "cropped_plate_url": plate_image_url,
            "license_plate": license_plate,
            "confidence": confidence,
            "traffic_light_state": traffic_light_state.value,
            "violation_type": ViolationType.RED_LIGHT.value,
            "timestamp": timestamp.isoformat(),
            "processed": True,
            "vote_count": vote_count,
            "vote_percent": vote_percent,
            "total_frames": total_frames,
            "track_id": track_id,
            "image_quality_score": image_quality_score,
            "processing_time_ms": processing_time_ms,
            "bbox_x": bbox_x,
            "bbox_y": bbox_y,
            "bbox_w": bbox_w,
            "bbox_h": bbox_h,
        }
        data = {key: value for key, value in data.items() if value is not None}

        response = self._db.table("violations").insert(data).execute()
        if response.data:
            logger.info(
                "Đã tạo vi phạm camera=%s biển=%s votes=%s/%s",
                camera_id,
                license_plate or "không rõ",
                vote_count,
                total_frames,
            )
            return response.data[0]
        raise RuntimeError("Không thể lưu vi phạm vào Supabase")

    async def _is_duplicate(self, camera_id: int, license_plate: str, timestamp: datetime) -> bool:
        window_start = timestamp - timedelta(seconds=self._dedup_window)
        response = (
            self._db.table("violations")
            .select("id")
            .eq("camera_id", camera_id)
            .eq("license_plate", license_plate)
            .gte("timestamp", window_start.isoformat())
            .lte("timestamp", timestamp.isoformat())
            .execute()
        )
        return bool(response.data)

    async def get_violations(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        query = self._db.from_("view_violations_full").select("*").order("timestamp", desc=True)
        if filters:
            if "camera_id" in filters:
                query = query.eq("camera_id", filters["camera_id"])
            if "license_plate" in filters:
                query = query.ilike("license_plate", f"%{filters['license_plate']}%")
            if "start_date" in filters:
                query = query.gte("timestamp", filters["start_date"])
            if "end_date" in filters:
                query = query.lte("timestamp", filters["end_date"])
        return query.range(offset, offset + limit - 1).execute().data or []

    async def get_by_id(self, violation_id: int) -> Optional[Dict]:
        response = (
            self._db.from_("view_violations_full")
            .select("*")
            .eq("id", violation_id)
            .single()
            .execute()
        )
        return response.data

    async def delete(self, violation_id: int) -> bool:
        response = self._db.table("violations").delete().eq("id", violation_id).execute()
        return bool(response.data)
