"""
repositories/camera_repo.py — Data access layer cho Camera + Provisioning + Zones
Tất cả query Supabase ở đây — không có business logic.
"""
from typing import Optional, List, Dict, Any
from database.supabase_client import get_supabase


class CameraRepository:
    """Thao tác CRUD camera và provisioning"""

    def __init__(self):
        self.db = get_supabase()

    # ---- cameras ----------------------------------------

    def get_all(self) -> List[Dict]:
        res = self.db.from_("view_camera_summary").select("*").order("camera_id").execute()
        return res.data or []

    def get_by_id(self, camera_id: int) -> Optional[Dict]:
        res = (self.db.from_("view_camera_summary")
               .select("*")
               .eq("camera_id", camera_id)
               .single()
               .execute())
        return res.data

    def create(self, data: Dict) -> Optional[Dict]:
        res = self.db.from_("cameras").insert(data).execute()
        return res.data[0] if res.data else None

    def update(self, camera_id: int, data: Dict) -> Optional[Dict]:
        res = (self.db.from_("cameras")
               .update(data)
               .eq("camera_id", camera_id)
               .execute())
        return res.data[0] if res.data else None

    def delete(self, camera_id: int) -> bool:
        res = self.db.from_("cameras").delete().eq("camera_id", camera_id).execute()
        return bool(res.data)

    def exists(self, camera_id: int) -> bool:
        res = (self.db.from_("cameras")
               .select("camera_id")
               .eq("camera_id", camera_id)
               .execute())
        return bool(res.data)

    # ---- provisioning -----------------------------------

    def upsert_provisioning(self, data: Dict) -> Optional[Dict]:
        """Insert hoặc update provisioning info"""
        res = (self.db.from_("camera_provisioning")
               .upsert(data, on_conflict="camera_id")
               .execute())
        return res.data[0] if res.data else None

    def get_provisioning(self, camera_id: int) -> Optional[Dict]:
        res = (self.db.from_("camera_provisioning")
               .select("*")
               .eq("camera_id", camera_id)
               .single()
               .execute())
        return res.data

    def touch_last_seen(self, camera_id: int) -> None:
        """Cập nhật last_seen_at + online=true"""
        from datetime import datetime, timezone
        self.db.from_("camera_provisioning").upsert(
            {"camera_id": camera_id,
             "last_seen_at": datetime.now(timezone.utc).isoformat(),
             "online": True},
            on_conflict="camera_id"
        ).execute()

    # ---- detection zones --------------------------------

    def get_zones(self, camera_id: int) -> List[Dict]:
        res = (self.db.from_("detection_zones")
               .select("*")
               .eq("camera_id", camera_id)
               .eq("active", True)
               .order("created_at")
               .execute())
        return res.data or []

    def replace_zones(self, camera_id: int, zones: List[Dict]) -> List[Dict]:
        """Xóa zone cũ, thêm zone mới (atomic)"""
        self.db.from_("detection_zones").delete().eq("camera_id", camera_id).execute()
        if not zones:
            return []
        for z in zones:
            z["camera_id"] = camera_id
        res = self.db.from_("detection_zones").insert(zones).execute()
        return res.data or []
