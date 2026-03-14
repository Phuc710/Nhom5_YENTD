"""
api/dashboard.py - Dedicated endpoints for the police monitoring dashboard.
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
