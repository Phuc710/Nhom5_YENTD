"""
services/dashboard_service.py - Data aggregation for police dashboard.
"""
from typing import Dict, List
from datetime import datetime

from repositories.camera_repo import CameraRepository
from repositories.violation_repo import ViolationRepository


class DashboardService:
    """Aggregate camera and violation data for the monitoring dashboard."""

    def __init__(self):
        self._camera_repo = CameraRepository()
        self._violation_repo = ViolationRepository()

    def get_overview(self) -> Dict:
        cameras = self._camera_repo.get_all()
        return {
            "total_cameras": len(cameras),
            "online_cameras": sum(1 for camera in cameras if camera.get("online")),
            "offline_cameras": sum(1 for camera in cameras if not camera.get("online")),
            "violations_today": self._violation_repo.get_today_count(),
            "violations_total": self._violation_repo.count(),
            "generated_at": datetime.now().isoformat(),
        }

    def get_cameras(self) -> List[Dict]:
        return self._camera_repo.get_all()

    def get_recent_violations(self, limit: int = 10) -> List[Dict]:
        return self._violation_repo.get_recent(limit)
