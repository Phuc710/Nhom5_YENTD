"""
LocalSettingsService — Quản lý settings từ file JSON local.

Tại sao cần file này?
  - Load nhanh khi khởi động (không cần gọi DB/Supabase)
  - Persist settings giữa các lần restart (tắt/mở lại)
  - Override .env cho runtime config (ALPR thresholds, MQTT, timing, ...)
  - Không block — đọc/ghi file chạy atomic, minimal lock

File: data/app_settings.json
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("trafficcam.settings")

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "app_settings.json"


class LocalSettingsService:
    """
    Thread-safe JSON settings manager.
    Loaded once at startup, can be hot-reloaded or saved at runtime.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else _SETTINGS_PATH
        self._lock = threading.RLock()
        self._data: Dict = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load settings from JSON file. Returns True if successful."""
        with self._lock:
            if not self._path.exists():
                logger.warning(f"Settings file not found: {self._path}. Using defaults.")
                self._data = {}
                self._loaded = True
                return False
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self._loaded = True
                logger.info(f"Settings loaded from {self._path}")
                return True
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                self._data = {}
                self._loaded = True
                return False

    def save(self) -> bool:
        """Persist current in-memory settings back to JSON file (atomic write)."""
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(".json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                tmp.replace(self._path)   # atomic rename
                logger.debug(f"Settings saved to {self._path}")
                return True
            except Exception as e:
                logger.error(f"Failed to save settings: {e}")
                return False

    def reload(self) -> bool:
        """Hot-reload settings from disk (without restarting the app)."""
        return self.load()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Generic get / set
    # ------------------------------------------------------------------

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get a nested value by dot-path keys.
        Example: get("mqtt", "broker_host") -> "192.168.1.8"
        """
        with self._lock:
            node = self._data
            for k in keys:
                if not isinstance(node, dict) or k not in node:
                    return default
                node = node[k]
            return node

    def set(self, *keys_and_value, save: bool = True) -> bool:
        """
        Set a nested value. Last argument is the value, all before are keys.
        Example: set("mqtt", "broker_host", "192.168.1.100")

        Args:
            *keys_and_value: keys... + value
            save: auto-save to disk after set
        """
        if len(keys_and_value) < 2:
            return False
        *keys, value = keys_and_value
        with self._lock:
            node = self._data
            for k in keys[:-1]:
                if k not in node or not isinstance(node[k], dict):
                    node[k] = {}
                node = node[k]
            node[keys[-1]] = value
            if save:
                return self.save()
            return True

    def get_section(self, *keys: str) -> Dict:
        """Get an entire section as a dict copy."""
        val = self.get(*keys, default={})
        return dict(val) if isinstance(val, dict) else {}

    def update_section(self, *keys_and_data, save: bool = True) -> bool:
        """
        Merge-update a section with new data.
        Example: update_section("alpr", {"vconf": 0.7, "pconf": 0.3})
        """
        if len(keys_and_data) < 2:
            return False
        *keys, data = keys_and_data
        with self._lock:
            node = self._data
            for k in keys[:-1]:
                if k not in node or not isinstance(node[k], dict):
                    node[k] = {}
                node = node[k]
            if keys and isinstance(node.get(keys[-1]), dict):
                node[keys[-1]].update(data)
            else:
                node[keys[-1]] = data
            if save:
                return self.save()
            return True

    # ------------------------------------------------------------------
    # Semantic helpers — ALPR
    # ------------------------------------------------------------------

    def get_alpr_config(self) -> Dict:
        return self.get_section("alpr")

    def update_alpr_config(self, updates: Dict, save: bool = True) -> bool:
        return self.update_section("alpr", updates, save=save)

    # ------------------------------------------------------------------
    # Semantic helpers — Traffic Light
    # ------------------------------------------------------------------

    def get_traffic_default_timings(self) -> Dict:
        return self.get_section("traffic_light", "default_timings")

    def get_camera_traffic_timings(self, camera_id: int) -> Dict:
        """Camera-specific timings (fallback to default if not set)."""
        cam = self.get("cameras", str(camera_id), default={})
        return cam.get("traffic_timing") or self.get_traffic_default_timings()

    def set_camera_traffic_timings(self, camera_id: int, timings: Dict, save: bool = True) -> bool:
        return self.set("cameras", str(camera_id), "traffic_timing", timings, save=save)

    def get_pcb_device(self, device_name: str) -> Dict:
        return self.get_section("pcb_devices", device_name)

    def get_pcb_timings(self, device_name: str) -> Dict:
        """PCB device timings (fallback to default)."""
        pcb = self.get_pcb_device(device_name)
        return pcb.get("timings") or self.get_traffic_default_timings()

    def set_pcb_timings(self, device_name: str, timings: Dict, save: bool = True) -> bool:
        return self.update_section("pcb_devices", device_name, "timings", timings, save=save)

    def get_mqtt_topic(self, topic_key: str, device_name: str = "") -> str:
        """Resolve an MQTT topic template with device_name substitution."""
        template = self.get("mqtt", "topics", topic_key, default="")
        return template.replace("{device_name}", device_name) if device_name else template

    def get_traffic_light_cmd(self, mode: str) -> Dict:
        """Get the MQTT command JSON for a traffic light mode."""
        cmd = self.get("traffic_light", "modes", mode, default={})
        return dict(cmd)

    # ------------------------------------------------------------------
    # Semantic helpers — Camera
    # ------------------------------------------------------------------

    def get_camera_config(self, camera_id: int) -> Dict:
        return self.get_section("cameras", str(camera_id))

    def get_camera_detection_zone(self, camera_id: int):
        return self.get("cameras", str(camera_id), "detect_zone", default=[])

    def get_camera_stop_line(self, camera_id: int):
        return self.get("cameras", str(camera_id), "stop_line", default=[])

    def set_camera_zones(self, camera_id: int, detect_zone=None, stop_line=None, save: bool = True) -> bool:
        updates = {}
        if detect_zone is not None:
            updates["detect_zone"] = detect_zone
        if stop_line is not None:
            updates["stop_line"] = stop_line
        return self.update_section("cameras", str(camera_id), updates, save=save)

    # ------------------------------------------------------------------
    # Semantic helpers — App state
    # ------------------------------------------------------------------

    def is_app_enabled(self) -> bool:
        return bool(self.get("app", "enabled", default=True))

    def set_app_enabled(self, enabled: bool, save: bool = True) -> bool:
        return self.set("app", "enabled", enabled, save=save)

    def get_all(self) -> Dict:
        """Return full settings dict (copy)."""
        with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy


# Global singleton
local_settings = LocalSettingsService()
