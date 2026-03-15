"""
services/dashboard_service.py - Data aggregation for police dashboard.
"""
from typing import Dict, List
from datetime import datetime

from backend.repositories.camera_repository import CameraRepository
from backend.repositories.violation_repository import ViolationRepository


class DashboardService:
    """Aggregate camera and violation data for the monitoring dashboard."""

    def __init__(self):
        self._camera_repository = CameraRepository()
        self._violation_repository = ViolationRepository()

    def get_overview(self) -> Dict:
        cameras = self._camera_repository.get_status_list()
        return {
            "total_cameras": len(cameras),
            "online_cameras": sum(1 for camera in cameras if camera.get("online")),
            "offline_cameras": sum(1 for camera in cameras if not camera.get("online")),
            "violations_today": self._violation_repository.get_today_count(),
            "violations_total": self._violation_repository.count(),
            "generated_at": datetime.now().isoformat(),
        }

    def get_cameras(self) -> List[Dict]:
        return self._camera_repository.get_all()

    def get_recent_violations(self, limit: int = 10) -> List[Dict]:
        return self._violation_repository.get_recent(limit)

    def get_camera_stats(self) -> List[Dict]:
        """Thong ke vi pham theo tung camera."""
        return self._violation_repository.get_stats_by_camera()

    def get_today_hourly_stats(self) -> List[Dict]:
        """Thong ke vi pham theo gio trong ngay hom nay."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._violation_repository.get_hourly_stats(today)
