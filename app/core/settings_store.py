"""
settings_store.py — Lưu & nạp settings cục bộ dưới dạng JSON.

File: backend/data/app_settings.json
Schema:
{
  "cameras": {
    "<camera_id>": {
      "stop_line": [[x0, y0], [x1, y1]],      // normalized 0..1, hoặc null
      "detect_zone": [[x,y], ...],             // 4 điểm normalized, hoặc null
      "frame_w": 320,
      "frame_h": 240,
      "traffic_timing": {
        "red_ms": 5000,
        "yellow_ms": 2000,
        "green_ms": 7000
      }
    }
  }
}
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Đường dẫn file JSON ──────────────────────────────────────────────────────

_HERE = Path(__file__).resolve()
_SETTINGS_FILE = _HERE.parents[2] / "backend" / "data" / "app_settings.json"


# ── Internal helpers ─────────────────────────────────────────────────────────

def _load_raw() -> Dict[str, Any]:
    """Đọc toàn bộ JSON file. Trả về dict rỗng nếu chưa có."""
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[SettingsStore] Không đọc được file settings: %s", exc)
        return {}


def _save_raw(data: Dict[str, Any]) -> None:
    """Ghi toàn bộ dict xuống JSON file (indent=2 cho dễ đọc)."""
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("[SettingsStore] Đã lưu → %s", _SETTINGS_FILE)
    except Exception as exc:
        logger.error("[SettingsStore] Lỗi ghi file settings: %s", exc)


def _cam_key(camera_id: int) -> str:
    return str(camera_id)


# ── ndarray ↔ list helpers ───────────────────────────────────────────────────

def _arr_to_list(arr: Optional[np.ndarray]) -> Optional[list]:
    if arr is None:
        return None
    return arr.tolist()


def _list_to_arr(lst: Optional[list]) -> Optional[np.ndarray]:
    if lst is None:
        return None
    return np.array(lst, dtype=np.float32)


# ── Public API ────────────────────────────────────────────────────────────────

def save_zones(camera_id: int, zones: Dict[str, Any]) -> None:
    """
    Lưu zones của camera vào JSON.

    zones format (từ StreamView.get_zones_np()):
        {
            "stop_line":   np.ndarray shape (2,2) hoặc None,
            "detect_zone": np.ndarray shape (4,2) hoặc None,
            "frame_w":     int,
            "frame_h":     int,
        }
    """
    data = _load_raw()
    cameras = data.setdefault("cameras", {})
    cam = cameras.setdefault(_cam_key(camera_id), {})

    cam["stop_line"]   = _arr_to_list(zones.get("stop_line"))
    cam["detect_zone"] = _arr_to_list(zones.get("detect_zone"))
    cam["frame_w"]     = int(zones.get("frame_w") or 320)
    cam["frame_h"]     = int(zones.get("frame_h") or 240)

    _save_raw(data)
    logger.info("[SettingsStore] Zones cam=%s đã lưu", camera_id)


def load_zones(camera_id: int) -> Dict[str, Any]:
    """
    Nạp zones của camera từ JSON.

    Trả về dict cùng format với StreamView.get_zones_np():
        {
            "stop_line":   np.ndarray hoặc None,
            "detect_zone": np.ndarray hoặc None,
            "frame_w":     int,
            "frame_h":     int,
        }
    """
    data    = _load_raw()
    cam     = data.get("cameras", {}).get(_cam_key(camera_id), {})
    return {
        "stop_line":   _list_to_arr(cam.get("stop_line")),
        "detect_zone": _list_to_arr(cam.get("detect_zone")),
        "frame_w":     int(cam.get("frame_w", 320)),
        "frame_h":     int(cam.get("frame_h", 240)),
    }


def save_traffic_timing(camera_id: int, red_ms: int, yellow_ms: int, green_ms: int) -> None:
    """Lưu timing đèn giao thông của camera."""
    data = _load_raw()
    cameras = data.setdefault("cameras", {})
    cam = cameras.setdefault(_cam_key(camera_id), {})
    cam["traffic_timing"] = {
        "red_ms":    red_ms,
        "yellow_ms": yellow_ms,
        "green_ms":  green_ms,
    }
    _save_raw(data)
    logger.info("[SettingsStore] Timing cam=%s đã lưu: R=%d Y=%d G=%d",
                camera_id, red_ms, yellow_ms, green_ms)


def load_traffic_timing(camera_id: int) -> Dict[str, int]:
    """
    Nạp timing đèn. Trả về dict:
        {"red_ms": 5000, "yellow_ms": 2000, "green_ms": 7000}
    """
    data = _load_raw()
    cam  = data.get("cameras", {}).get(_cam_key(camera_id), {})
    timing = cam.get("traffic_timing", {})
    return {
        "red_ms":    int(timing.get("red_ms",    5000)),
        "yellow_ms": int(timing.get("yellow_ms", 2000)),
        "green_ms":  int(timing.get("green_ms",  7000)),
    }
