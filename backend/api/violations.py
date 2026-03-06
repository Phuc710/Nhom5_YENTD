"""
api/violations.py — Violation REST API
  GET  /api/violations          — Danh sách (filter + pagination)
  GET  /api/violations/{id}     — Chi tiết
  GET  /api/violations/stats    — Thống kê dashboard
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from repositories.violation_repo import ViolationRepository
from models.violation import ViolationResponse, ViolationFilter

router = APIRouter(prefix="/violations", tags=["Violations"])
_repo = ViolationRepository()


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
    """Tổng hợp cho Dashboard"""
    from repositories.camera_repo import CameraRepository
    cameras = CameraRepository().get_all()
    total_cameras  = len(cameras)
    online_cameras = sum(1 for c in cameras if c.get("online"))
    total_today    = _repo.get_today_count()
    total_all      = _repo.count()
    recent         = _repo.get_recent(5)
    return {
        "total_cameras": total_cameras,
        "online_cameras": online_cameras,
        "violations_today": total_today,
        "violations_total": total_all,
        "recent_violations": recent,
    }


@router.get("/{violation_id}", response_model=ViolationResponse)
async def get_violation(violation_id: int):
    v = _repo.get_by_id(violation_id)
    if v is None:
        raise HTTPException(404, f"Vi phạm {violation_id} không tồn tại")
    return v
