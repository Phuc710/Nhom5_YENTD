"""
api/stats.py — Thống kê tổng quan
GET /api/stats              — Overall stats (today/week/month)
GET /api/stats/by-camera    — Stats theo camera
GET /api/stats/by-hour      — Vi phạm theo giờ
"""
from fastapi import APIRouter, Query
from datetime import datetime, timedelta

from database.supabase_client import get_supabase
from utils.logger import get_logger

router = APIRouter(prefix="/stats", tags=["Stats"])
logger = get_logger(__name__)


def _count(table: str, gte_field: str = None, gte_val: str = None) -> int:
    db  = get_supabase()
    q   = db.table(table).select("id", count="exact")
    if gte_field:
        q = q.gte(gte_field, gte_val)
    res = q.execute()
    return res.count or 0


@router.get("")
async def get_stats():
    """Tổng hợp vi phạm: hôm nay / tuần / tháng"""
    now         = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start  = (now - timedelta(days=7)).isoformat()
    month_start = (now - timedelta(days=30)).isoformat()

    db = get_supabase()

    def cnt(gte=None):
        q = db.table("violations").select("id", count="exact")
        if gte:
            q = q.gte("timestamp", gte)
        return q.execute().count or 0

    return {
        "total_violations": cnt(),
        "today_violations": cnt(today_start),
        "week_violations":  cnt(week_start),
        "month_violations": cnt(month_start),
    }


@router.get("/by-camera")
async def stats_by_camera():
    """Vi phạm theo từng camera — dùng view_daily_stats"""
    db  = get_supabase()
    res = db.from_("view_camera_summary").select("camera_id,camera_name,violations_today,violations_total").execute()
    return res.data or []


@router.get("/by-hour")
async def stats_by_hour(days: int = Query(7, ge=1, le=90)):
    """Vi phạm theo giờ trong N ngày qua"""
    db         = get_supabase()
    start_date = (datetime.now() - timedelta(days=days)).isoformat()
    res        = db.table("violations").select("timestamp").gte("timestamp", start_date).execute()

    hour_counts: dict = {}
    for row in (res.data or []):
        try:
            ts   = datetime.fromisoformat(row["timestamp"])
            hour = ts.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        except Exception:
            pass

    return [{"hour": h, "count": c} for h, c in sorted(hour_counts.items())]


@router.get("/daily")
async def stats_daily():
    """Vi phạm theo ngày — từ view_daily_stats"""
    db  = get_supabase()
    res = db.from_("view_daily_stats").select("*").limit(90).execute()
    return res.data or []
