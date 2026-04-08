"""
DBService — Supabase CRUD operations for all tables.

Uses supabase-py client with service_role key for full access.
All methods are synchronous (supabase-py is sync); async wrappers
can be added later if needed.
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from api.config import settings

logger = logging.getLogger("trafficcam.db")


class DBService:
    """Supabase database service — CRUD for cameras, violations, zones, settings."""

    def __init__(self) -> None:
        self._client = None

    def startup(self) -> None:
        """Initialize Supabase client. Called during app lifespan."""
        if not settings.supabase_configured:
            logger.warning(
                "Supabase not configured (TRAFFIC_SUPABASE_URL / TRAFFIC_SUPABASE_KEY missing). "
                "Database features disabled."
            )
            return

        try:
            from supabase import create_client
            self._client = create_client(settings.supabase_url, settings.supabase_key)
            logger.info("Supabase client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self._client = None

    def shutdown(self) -> None:
        """Release Supabase client."""
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ===================================================================
    # CAMERAS
    # ===================================================================

    def list_cameras(self) -> List[Dict]:
        """List all cameras from view_camera_summary."""
        if not self._client:
            return []
        try:
            resp = self._client.table("cameras").select(
                "*, camera_provisioning(*)"
            ).order("camera_id").execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"list_cameras error: {e}")
            return []

    def get_camera_summary(self) -> List[Dict]:
        """Get camera summary view (includes violation counts)."""
        if not self._client:
            return []
        try:
            resp = self._client.from_("view_camera_summary").select("*").execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"get_camera_summary error: {e}")
            return []

    def get_camera(self, camera_id: int) -> Optional[Dict]:
        """Get single camera with provisioning info."""
        if not self._client:
            return None
        try:
            resp = self._client.table("cameras").select(
                "*, camera_provisioning(*)"
            ).eq("camera_id", camera_id).single().execute()
            return resp.data
        except Exception as e:
            logger.error(f"get_camera({camera_id}) error: {e}")
            return None

    def create_camera(self, data: Dict) -> Optional[Dict]:
        """Insert a new camera."""
        if not self._client:
            return None
        try:
            resp = self._client.table("cameras").insert(data).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"create_camera error: {e}")
            return None

    def update_camera(self, camera_id: int, data: Dict) -> Optional[Dict]:
        """Update camera fields."""
        if not self._client:
            return None
        try:
            resp = self._client.table("cameras").update(data).eq(
                "camera_id", camera_id
            ).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"update_camera({camera_id}) error: {e}")
            return None

    def delete_camera(self, camera_id: int) -> bool:
        """Delete a camera (cascades to provisioning, zones, violations)."""
        if not self._client:
            return False
        try:
            self._client.table("cameras").delete().eq(
                "camera_id", camera_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"delete_camera({camera_id}) error: {e}")
            return False

    def upsert_provisioning(self, camera_id: int, data: Dict) -> Optional[Dict]:
        """Insert or update provisioning data for a camera (ESP32-S3 self-register)."""
        if not self._client:
            return None
        data["camera_id"] = camera_id
        data["updated_at"] = datetime.utcnow().isoformat()
        try:
            resp = self._client.table("camera_provisioning").upsert(
                data, on_conflict="camera_id"
            ).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"upsert_provisioning({camera_id}) error: {e}")
            return None

    # ===================================================================
    # VIOLATIONS
    # ===================================================================

    def list_violations(
        self,
        camera_id: Optional[int] = None,
        license_plate: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """List violations with optional filters, paginated."""
        if not self._client:
            return []
        try:
            query = self._client.from_("view_violations_full").select("*")
            if camera_id is not None:
                query = query.eq("camera_id", camera_id)
            if license_plate:
                query = query.ilike("license_plate", f"%{license_plate}%")
            query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)
            resp = query.execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"list_violations error: {e}")
            return []

    def get_violation(self, violation_id: int) -> Optional[Dict]:
        """Get single violation with full details."""
        if not self._client:
            return None
        try:
            resp = self._client.from_("view_violations_full").select("*").eq(
                "id", violation_id
            ).single().execute()
            return resp.data
        except Exception as e:
            logger.error(f"get_violation({violation_id}) error: {e}")
            return None

    def create_violation(self, data: Dict) -> Optional[Dict]:
        """Record a new violation."""
        if not self._client:
            return None
        try:
            resp = self._client.table("violations").insert(data).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"create_violation error: {e}")
            return None

    def create_ocr_result(self, data: Dict) -> Optional[Dict]:
        """Insert an OCR voting frame result."""
        if not self._client:
            return None
        try:
            resp = self._client.table("ocr_results").insert(data).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"create_ocr_result error: {e}")
            return None

    def get_daily_stats(self, camera_id: Optional[int] = None) -> List[Dict]:
        """Get daily violation stats."""
        if not self._client:
            return []
        try:
            query = self._client.from_("view_daily_stats").select("*")
            if camera_id is not None:
                query = query.eq("camera_id", camera_id)
            query = query.order("date_vn", desc=True).limit(90)
            resp = query.execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"get_daily_stats error: {e}")
            return []

    # ===================================================================
    # DETECTION ZONES
    # ===================================================================

    def list_zones(self, camera_id: Optional[int] = None) -> List[Dict]:
        """List detection zones, optionally filtered by camera."""
        if not self._client:
            return []
        try:
            query = self._client.table("detection_zones").select("*")
            if camera_id is not None:
                query = query.eq("camera_id", camera_id)
            query = query.order("created_at")
            resp = query.execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"list_zones error: {e}")
            return []

    def create_zone(self, data: Dict) -> Optional[Dict]:
        """Create a new detection zone."""
        if not self._client:
            return None
        try:
            resp = self._client.table("detection_zones").insert(data).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"create_zone error: {e}")
            return None

    def update_zone(self, zone_id: str, data: Dict) -> Optional[Dict]:
        """Update a detection zone."""
        if not self._client:
            return None
        try:
            resp = self._client.table("detection_zones").update(data).eq(
                "id", zone_id
            ).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"update_zone({zone_id}) error: {e}")
            return None

    def delete_zone(self, zone_id: str) -> bool:
        """Delete a detection zone."""
        if not self._client:
            return False
        try:
            self._client.table("detection_zones").delete().eq(
                "id", zone_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"delete_zone({zone_id}) error: {e}")
            return False

    # ===================================================================
    # SYSTEM SETTINGS
    # ===================================================================

    def list_settings(self) -> List[Dict]:
        """List all system settings."""
        if not self._client:
            return []
        try:
            resp = self._client.table("system_settings").select("*").order("key").execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"list_settings error: {e}")
            return []

    def get_setting(self, key: str) -> Optional[Dict]:
        """Get a specific system setting."""
        if not self._client:
            return None
        try:
            resp = self._client.table("system_settings").select("*").eq(
                "key", key
            ).single().execute()
            return resp.data
        except Exception as e:
            logger.error(f"get_setting({key}) error: {e}")
            return None

    def upsert_setting(self, key: str, value: Any, description: str = "") -> Optional[Dict]:
        """Insert or update a system setting."""
        if not self._client:
            return None
        data = {"key": key, "value": value}
        if description:
            data["description"] = description
        try:
            resp = self._client.table("system_settings").upsert(
                data, on_conflict="key"
            ).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"upsert_setting({key}) error: {e}")
            return None
