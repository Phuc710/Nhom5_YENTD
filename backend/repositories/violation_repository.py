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

    def get_hourly_stats(self, date_str: str) -> List[Dict]:
        """
        Lấy thống kê vi phạm theo giờ cho một ngày cụ thể bằng cách query và group trong Python.
        """
        try:
            # Query tất cả vi phạm trong ngày
            start_ts = f"{date_str}T00:00:00+07:00"
            end_ts = f"{date_str}T23:59:59+07:00"
            
            res = (
                self._db.from_("violations")
                .select("timestamp")
                .gte("timestamp", start_ts)
                .lte("timestamp", end_ts)
                .execute()
            )
            
            rows = res.data or []
            if not rows:
                return []
                
            # Group theo giờ (0-23)
            hourly_counts = {i: 0 for i in range(24)}
            for row in rows:
                ts_str = row.get("timestamp")
                if ts_str:
                    # ISO format: 2026-03-15T18:26:35+07:00
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        # Chuyển về múi giờ VN (+07) nếu cần, hoặc giả định DB đã lưu chuẩn iso
                        # Ở đây ta lấy hour trực tiếp
                        hourly_counts[dt.hour] += 1
                    except Exception:
                        continue
            
            return {
                f"{h:02d}": count
                for h, count in sorted(hourly_counts.items())
            }
        except Exception as exc:
            logger.error("Lỗi khi lấy thống kê theo giờ: %s", exc)
            return []

    def get_weekly_trend(self) -> List[Dict]:
        """Thong ke vi pham 7 ngay gan nhat."""
        from datetime import datetime, timedelta
        
        try:
            # Lay 7 ngay gan nhat
            days = []
            for i in range(6, -1, -1):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                days.append(date)
                
            start_date = days[0]
            res = (
                self._db.from_("violations")
                .select("timestamp")
                .gte("timestamp", f"{start_date}T00:00:00+07:00")
                .execute()
            )
            
            rows = res.data or []
            trend = {d: 0 for d in days}
            
            for row in rows:
                ts = row.get("timestamp")
                if ts:
                    d = ts.split("T")[0]
                    if d in trend:
                        trend[d] += 1
                        
            return [{"date": d, "count": count} for d, count in trend.items()]
        except Exception as exc:
            logger.error("Lỗi khi lấy thống kê tuần: %s", exc)
            return []
