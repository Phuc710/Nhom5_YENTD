"""
repositories/violation_repository.py - Data access layer Vi pham.
Dung view_violations_full de join camera info tu dong.
"""

from typing import Dict, List, Optional

from backend.database.supabase_client import get_supabase_read
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ViolationRepository:
    """Truy van Supabase cho bang/view vi pham."""

    def __init__(self):
        self._db = get_supabase_read()

    def get_all(
        self,
        camera_id: Optional[int] = None,
        license_plate: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> List[Dict]:
        query = (
            self._db.from_("view_violations_full")
            .select("*")
            .order("timestamp", desc=True)
        )
        if camera_id:
            query = query.eq("camera_id", camera_id)
        if license_plate:
            query = query.ilike("license_plate", f"%{license_plate}%")
        if date_from:
            query = query.gte("timestamp", f"{date_from}T00:00:00+07:00")
        if date_to:
            query = query.lte("timestamp", f"{date_to}T23:59:59+07:00")

        offset = (page - 1) * limit
        return query.range(offset, offset + limit - 1).execute().data or []

    def get_by_id(self, violation_id: int) -> Optional[Dict]:
        res = (
            self._db.from_("view_violations_full")
            .select("*")
            .eq("id", violation_id)
            .single()
            .execute()
        )
        return res.data

    def get_recent(self, limit: int = 10) -> List[Dict]:
        return (
            self._db.from_("view_violations_full")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
            .data or []
        )

    def count(self, camera_id: Optional[int] = None) -> int:
        query = self._db.table("violations").select("id", count="exact")
        if camera_id:
            query = query.eq("camera_id", camera_id)
        return query.execute().count or 0

    def get_today_count(self) -> int:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%dT00:00:00")
        return (
            self._db.table("violations")
            .select("id", count="exact")
            .gte("timestamp", today)
            .execute()
            .count or 0
        )

    def get_stats_by_camera(self) -> List[Dict]:
        return (
            self._db.from_("view_daily_stats")
            .select("*")
            .limit(100)
            .execute()
            .data or []
        )
