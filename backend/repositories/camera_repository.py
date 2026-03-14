"""
repositories/camera_repository.py - Data access layer cho Camera + Provisioning + Zones.
Tat ca query Supabase o day, khong co business logic.
"""

from typing import Any, Dict, List, Optional

from backend.database.supabase_client import get_supabase_read, get_supabase_write


CAMERA_SUMMARY_COLUMNS = ",".join(
    (
        "camera_id",
        "camera_name",
        "location",
        "latitude",
        "longitude",
        "stream_url",
        "tb_device_name",
        "status",
        "configured_camera_name",
        "configured_stream_url",
        "device_name",
        "project_name",
        "device_model",
        "wifi_ssid",
        "resolution",
        "stream_scheme",
        "stream_host",
        "stream_port",
        "stream_path",
        "stream_snapshot_path",
        "ip_address",
        "fw_version",
        "mac_address",
        "last_seen_at",
        "last_boot_at",
        "online",
        "violations_today",
        "violations_total",
    )
)

CAMERA_STATUS_COLUMNS = "camera_id,online"
CAMERA_LOOKUP_COLUMNS = ",".join(
    (
        "camera_id",
        "camera_name",
        "location",
        "stream_url",
        "tb_device_name",
        "status",
        "latitude",
        "longitude",
        "configured_camera_name",
        "configured_stream_url",
        "device_name",
        "project_name",
        "device_model",
        "wifi_ssid",
        "resolution",
        "stream_scheme",
        "stream_host",
        "stream_port",
        "stream_path",
        "stream_snapshot_path",
        "ip_address",
        "fw_version",
        "mac_address",
        "last_seen_at",
        "last_boot_at",
        "online",
        "violations_today",
        "violations_total",
    )
)

PROVISIONING_COLUMNS = ",".join(
    (
        "camera_id",
        "tb_device_id",
        "tb_device_name",
        "device_name",
        "project_name",
        "device_model",
        "wifi_ssid",
        "resolution",
        "access_token",
        "mac_address",
        "fw_version",
        "idf_version",
        "stream_scheme",
        "stream_host",
        "stream_port",
        "stream_path",
        "stream_snapshot_path",
        "ip_address",
        "last_seen_at",
        "last_boot_at",
        "online",
        "extra_attributes",
    )
)

PROVISIONING_LOOKUP_COLUMNS = "camera_id,tb_device_id,tb_device_name,mac_address"


class CameraRepository:
    """Thao tac CRUD camera va provisioning."""

    def __init__(self):
        self.read_db = get_supabase_read()
        self.write_db = get_supabase_write()

    # ---- cameras ----------------------------------------

    def get_all(self) -> List[Dict]:
        res = (
            self.read_db.from_("view_camera_summary")
            .select(CAMERA_SUMMARY_COLUMNS)
            .order("camera_id")
            .execute()
        )
        return res.data or []

    def get_status_list(self) -> List[Dict]:
        res = (
            self.read_db.from_("view_camera_summary")
            .select(CAMERA_STATUS_COLUMNS)
            .order("camera_id")
            .execute()
        )
        return res.data or []

    def get_by_id(self, camera_id: int) -> Optional[Dict]:
        res = (
            self.read_db.from_("view_camera_summary")
            .select(CAMERA_SUMMARY_COLUMNS)
            .eq("camera_id", camera_id)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def get_by_tb_device_name(self, tb_device_name: str) -> Optional[Dict]:
        if not tb_device_name:
            return None
        res = (
            self.read_db.from_("view_camera_summary")
            .select(CAMERA_LOOKUP_COLUMNS)
            .eq("tb_device_name", tb_device_name)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def create(self, data: Dict) -> Optional[Dict]:
        res = self.write_db.from_("cameras").insert(data).execute()
        return res.data[0] if res.data else None

    def update(self, camera_id: int, data: Dict) -> Optional[Dict]:
        res = (
            self.write_db.from_("cameras")
            .update(data)
            .eq("camera_id", camera_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def delete(self, camera_id: int) -> bool:
        res = self.write_db.from_("cameras").delete().eq("camera_id", camera_id).execute()
        return bool(res.data)

    def exists(self, camera_id: int) -> bool:
        res = (
            self.read_db.from_("cameras")
            .select("camera_id")
            .eq("camera_id", camera_id)
            .execute()
        )
        return bool(res.data)

    def get_next_camera_id(self) -> int:
        res = (
            self.read_db.from_("cameras")
            .select("camera_id")
            .order("camera_id", desc=True)
            .limit(1)
            .execute()
        )
        data = res.data or []
        if not data:
            return 1
        return int(data[0]["camera_id"]) + 1

    # ---- provisioning -----------------------------------

    def upsert_provisioning(self, data: Dict) -> Optional[Dict]:
        """Insert hoac update provisioning info."""
        res = (
            self.write_db.from_("camera_provisioning")
            .upsert(data, on_conflict="camera_id")
            .execute()
        )
        return res.data[0] if res.data else None

    def get_provisioning(self, camera_id: int) -> Optional[Dict]:
        res = (
            self.read_db.from_("camera_provisioning")
            .select(PROVISIONING_COLUMNS)
            .eq("camera_id", camera_id)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def get_provisioning_many(self, camera_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not camera_ids:
            return {}
        res = (
            self.read_db.from_("camera_provisioning")
            .select(PROVISIONING_COLUMNS)
            .in_("camera_id", camera_ids)
            .execute()
        )
        rows = res.data or []
        return {int(row["camera_id"]): row for row in rows if row.get("camera_id") is not None}

    def get_provisioning_by_tb_device_name(self, tb_device_name: str) -> Optional[Dict]:
        if not tb_device_name:
            return None
        res = (
            self.read_db.from_("camera_provisioning")
            .select(PROVISIONING_LOOKUP_COLUMNS)
            .eq("tb_device_name", tb_device_name)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def get_provisioning_by_mac(self, mac_address: str) -> Optional[Dict]:
        if not mac_address:
            return None
        res = (
            self.read_db.from_("camera_provisioning")
            .select(PROVISIONING_LOOKUP_COLUMNS)
            .eq("mac_address", mac_address)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def touch_last_seen(self, camera_id: int) -> None:
        """Cap nhat last_seen_at + online=true."""
        from datetime import datetime, timezone

        self.write_db.from_("camera_provisioning").upsert(
            {
                "camera_id": camera_id,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "online": True,
            },
            on_conflict="camera_id",
        ).execute()

    # ---- detection zones --------------------------------

    def get_zones(self, camera_id: int) -> List[Dict]:
        res = (
            self.read_db.from_("detection_zones")
            .select("*")
            .eq("camera_id", camera_id)
            .eq("active", True)
            .order("created_at")
            .execute()
        )
        return res.data or []

    def replace_zones(self, camera_id: int, zones: List[Dict]) -> List[Dict]:
        """Xoa zone cu, them zone moi."""
        self.write_db.from_("detection_zones").delete().eq("camera_id", camera_id).execute()
        if not zones:
            return []
        for zone in zones:
            zone["camera_id"] = camera_id
        res = self.write_db.from_("detection_zones").insert(zones).execute()
        return res.data or []
