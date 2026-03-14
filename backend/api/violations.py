"""Violation REST API cho danh sách, chi tiết và bản ghi gần nhất."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.models.violation import ViolationResponse
from backend.repositories.violation_repository import ViolationRepository

router = APIRouter(prefix="/violations", tags=["Violations"])
violation_repository = ViolationRepository()


@router.get("", response_model=List[ViolationResponse])
async def list_violations(
    camera_id: Optional[int] = Query(None),
    license_plate: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    return violation_repository.get_all(
        camera_id=camera_id,
        license_plate=license_plate,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )


@router.get("/recent", response_model=List[ViolationResponse])
async def get_recent(limit: int = Query(10, ge=1, le=50)):
    return violation_repository.get_recent(limit)


@router.get("/{violation_id}", response_model=ViolationResponse)
async def get_violation(violation_id: int):
    violation = violation_repository.get_by_id(violation_id)
    if violation is None:
        raise HTTPException(404, f"Vi phạm {violation_id} không tồn tại")
    return violation
