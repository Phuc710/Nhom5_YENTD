"""
api/violations.py — Violation REST API
  GET  /api/violations          — Danh sách (filter + pagination)
  GET  /api/violations/{id}     — Chi tiết
  GET  /api/violations/stats    — Thống kê dashboard
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from repositories.violation_repo import ViolationRepository
from services.dashboard_service import DashboardService
from models.violation import ViolationResponse, ViolationFilter

router = APIRouter(prefix="/violations", tags=["Violations"])
_repo = ViolationRepository()
_dashboard_svc = DashboardService()


@router.get("", response_model=List[ViolationResponse])
async def list_violations(
    camera_id:     Optional[int] = Query(None),
    license_plate: Optional[str] = Query(None),
    date_from:     Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:       Optional[str] = Query(None, description="YYYY-MM-DD"),
    page:          int           = Query(1, ge=1),
    limit:         int           = Query(20, ge=1, le=100),
):
    return _repo.get_all(
        camera_id=camera_id,
        license_plate=license_plate,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )


@router.get("/recent", response_model=List[ViolationResponse])
async def get_recent(limit: int = Query(10, ge=1, le=50)):
    return _repo.get_recent(limit)


@router.get("/stats/daily")
async def get_daily_stats():
    return _repo.get_stats_by_camera()


@router.get("/stats/summary")
async def get_summary():
    """Legacy summary endpoint kept for v1 compatibility."""
    payload = _dashboard_svc.get_overview()
    payload["recent_violations"] = _dashboard_svc.get_recent_violations(5)
    return payload


@router.get("/{violation_id}", response_model=ViolationResponse)
async def get_violation(violation_id: int):
    v = _repo.get_by_id(violation_id)
    if v is None:
        raise HTTPException(404, f"Vi phạm {violation_id} không tồn tại")
    return v
