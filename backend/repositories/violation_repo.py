"""
repositories/violation_repo.py — Data access layer Vi phạm
Dùng view_violations_full để join camera info tự động.
"""
from typing import Optional, List, Dict
from database.supabase_client import get_supabase
from utils.logger import get_logger

logger = get_logger(__name__)


class ViolationRepository:
    """Truy vấn Supabase cho bảng violations"""

    def __init__(self):
        self._db = get_supabase()

    def get_all(
        self,
        camera_id:     Optional[int] = None,
        license_plate: Optional[str] = None,
        date_from:     Optional[str] = None,
        date_to:       Optional[str] = None,
        page:  int = 1,
        limit: int = 20,
    ) -> List[Dict]:
        q = (
            self._db.from_("view_violations_full")
            .select("*")
            .order("timestamp", desc=True)
        )
        if camera_id:     q = q.eq("camera_id", camera_id)
        if license_plate: q = q.ilike("license_plate", f"%{license_plate}%")
        if date_from:     q = q.gte("timestamp", f"{date_from}T00:00:00+07:00")
        if date_to:       q = q.lte("timestamp", f"{date_to}T23:59:59+07:00")

        offset = (page - 1) * limit
        return q.range(offset, offset + limit - 1).execute().data or []

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
        q = self._db.table("violations").select("id", count="exact")
        if camera_id:
            q = q.eq("camera_id", camera_id)
        return q.execute().count or 0

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
