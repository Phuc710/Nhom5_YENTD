"""
api/dashboard.py - Các endpoint dành riêng cho dashboard giám sát của công an.
"""
from fastapi import APIRouter, Query

from backend.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
_svc = DashboardService()


@router.get("/overview")
async def get_overview():
    return _svc.get_overview()


@router.get("/cameras")
async def get_dashboard_cameras():
    return _svc.get_cameras()


@router.get("/recent-violations")
async def get_recent_violations(limit: int = Query(10, ge=1, le=50)):
    return _svc.get_recent_violations(limit)


@router.get("/stats/camera")
async def get_camera_stats():
    """Lấy thống kê vi phạm theo từng camera."""
    return _svc.get_camera_stats()


@router.get("/stats/hourly")
async def get_today_hourly_stats():
    """Lấy thống kê vi phạm theo giờ trong ngày."""
    return _svc.get_today_hourly_stats()
@router.get("/stats/weekly")
async def get_weekly_trend():
    """Lấy thống kê vi phạm 7 ngày gần nhất."""
    return _svc.get_weekly_trend()
