"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI TRAFFIC CONTROL — BACKEND SERVER v7.0 FULL                              ║
║  Flask + SocketIO + MQTT + SQLite + Virtual ESP32 Cluster                   ║
║                                                                              ║
║  TÍCH HỢP ĐẦY ĐỦ 16 FILE:                                                   ║
║    ✔ virtual_esp32_cluster.py  — Thay thế phần cứng ESP32                   ║
║    ✔ ai_engine.py              — AI phát hiện xe + OCR license plate              ║
║    ✔ csv_importer.py           — Import/Export violations CSV                  ║
║    ✔ image_processor.py        — Xử lý ảnh camera                          ║
║    ✔ schema.sql                — Cấu trúc database SQLite                   ║
║    ✔ seed_database.py          — Dữ liệu mẫu cho testing                    ║
║    ✔ main.html / main.css / main.js   — Dashboard chính                     ║
║    ✔ login.html / login.css / login.js — Trang xác thực                     ║
║    ✔ index.html                — Màn hình boot                              ║
║                                                                              ║
║  LUỒNG DỮ LIỆU THẬT (v7.0):                                                 ║
║    ESP32-CAM → MQTT:1883 → app.py                                           ║
║    app.py → YOLO detect → OCR → imge/<plate>_<ts>.jpg                       ║
║    app.py → SQLite (violations) → SocketIO → Dashboard                      ║
║    Camera IP → POST /api/upload-violation → process_violation               ║
║                                                                              ║
║  7 GIỚI HẠN NGỮ CẢNH TỐI ƯU ESP32:                                         ║
║    GH1 Vận tốc        < 20 km/h   GH2 ≤ 6 xe/frame                        ║
║    GH3 Thời tiết      Nắng/Mưa nhẹ/Đủ sáng                                 ║
║    GH4 Khoảng cách    5m           GH5 ROI STOP_LINE                        ║
║    GH6 Chụp 500ms — chỉ khi ĐỎ   GH7 Xe máy & Ô tô                        ║
║                                                                              ║
║  API ENDPOINTS MỚI (v7.0):                                                  ║
║    GET  /api/violations/latest              — 10 violations mới (polling)      ║
║    GET  /api/device-status                  — trạng thái device           ║
║    POST /api/upload-violation               — upload ảnh từ camera thật     ║
║    POST /api/violations/<id>/replace-plate-image — thay ảnh license plate        ║
║    POST /api/violations/<id>/replace-full-image  — thay ảnh gốc            ║
║    PUT  /api/violations/<id>  (mở rộng)     — sửa plate_text (admin)       ║
║                                                                              ║
║  DATA RETENTION:                                                             ║
║    > 30 ngày → EXPIRED (ẩn khỏi dashboard)                                 ║
║    > 90 ngày → DELETED (xóa mềm)                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os, time, json, sqlite3, threading, logging, base64, re, importlib.util, sys as _sys
import socket as _socket
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests
from flask import Flask, request, jsonify, send_from_directory, Response, g
from flask_socketio import SocketIO, emit


def _configure_stdio_utf8():
    """
    Windows consoles can use legacy code pages (e.g., cp1258) that cannot print
    box-drawing characters used by the startup banner. Force UTF-8 output and
    replace unencodable characters as a last resort.
    """
    try:
        if hasattr(_sys.stdout, "reconfigure"):
            _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(_sys.stderr, "reconfigure"):
            _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_configure_stdio_utf8()

# ════════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("TrafficAI")

# ════════════════════════════════════════════════════════════════
# PATHS — Serve frontend from the same directory as app.py
# ════════════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent

# ════════════════════════════════════════════════════════════════
# ENV LOADER — read server/config.env (if present)
# ════════════════════════════════════════════════════════════════
def _load_env_file(path: Path) -> None:
    try:
        if not path.exists():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            os.environ.setdefault(k, v)
    except Exception:
        pass


_load_env_file(BASE_DIR / "config.env")

# Frontend assets live in the repo-level `DEVELOPER/` folder in this workspace.
# Keep a fallback to `server/` for older layouts, and allow overriding via env var.
_frontend_env = os.getenv("FRONTEND_DIR")
if _frontend_env:
    FRONTEND_DIR = Path(_frontend_env).expanduser().resolve()
else:
    _frontend_candidate = BASE_DIR.parent / "DEVELOPER"
    if all((_frontend_candidate / f).exists() for f in ("main.html", "login.html", "index.html")):
        FRONTEND_DIR = _frontend_candidate
    else:
        FRONTEND_DIR = BASE_DIR

IMAGE_DIR = REPO_DIR / "imge"
# Legacy layout: older versions wrote images under `server/imge/`.
LEGACY_IMAGE_DIR = BASE_DIR / "imge"
DB_PATH = BASE_DIR / "traffic_ai.db"

# Create image directories
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

def _maybe_migrate_legacy_images() -> None:
    """
    One-time, best-effort copy from legacy `server/imge/` to repo-level `imge/`.
    This prevents broken links when upgrading layouts.
    """
    try:
        if LEGACY_IMAGE_DIR.resolve() == IMAGE_DIR.resolve():
            return
        for sub in ("violations",):
            src_dir = LEGACY_IMAGE_DIR / sub
            dst_dir = IMAGE_DIR / sub
            if not src_dir.exists():
                continue
            for f in src_dir.glob("*.*"):
                if not f.is_file():
                    continue
                dst = dst_dir / f.name
                if not dst.exists():
                    try:
                        dst.write_bytes(f.read_bytes())
                    except Exception:
                        pass
        # Also copy top-level assets (e.g., admin.jpg for login)
        for f in LEGACY_IMAGE_DIR.glob("*.*"):
            if not f.is_file():
                continue
            dst = IMAGE_DIR / f.name
            if not dst.exists():
                try:
                    dst.write_bytes(f.read_bytes())
                except Exception:
                    pass
    except Exception:
        pass

_maybe_migrate_legacy_images()

_sample_viol_cache = {"mtime": 0.0, "rows": {}}  # canonical_plate -> row dict
_sample_sources_cache = {"rows": None}
_ocr_reader = None
_yolo_model = None  # ultralytics YOLO model cache (or False if unavailable)

def _canon_plate(s: str) -> str:
    s = (s or "").upper().strip()
    # Keep only A-Z0-9
    return "".join(ch for ch in s if ch.isalnum())

def _format_plate(canon: str) -> str:
    canon = _canon_plate(canon)
    if len(canon) < 6:
        return canon

    # Motorbike legacy format with dot: 49E199966 -> 49-E1 999.66
    m = re.fullmatch(r"(\d{2})([A-Z])(\d)(\d{5})", canon)
    if m:
        p2, letter, digit, tail = m.groups()
        return f"{p2}-{letter}{digit} {tail[:3]}.{tail[3:]}"

    # Common format: 51B12345 -> 51B-12345
    m2 = re.fullmatch(r"(\d{2})([A-Z])(\d{4,5})", canon)
    if m2:
        p2, letter, tail = m2.groups()
        return f"{p2}{letter}-{tail}"

    # Fallback: split after 3 or 4 when province code present
    if canon[:2].isdigit():
        prefix_len = 4 if len(canon) >= 4 and canon[3].isdigit() else 3
        if prefix_len < len(canon):
            return f"{canon[:prefix_len]}-{canon[prefix_len:]}"
    return canon

def _load_sample_violations() -> dict[str, dict]:
    """
    Load `server/sample_violations.csv` (if present) and cache by mtime.
    Matching uses canonical plate (A-Z0-9 only).
    """
    try:
        csv_path = BASE_DIR / "sample_violations.csv"
        if not csv_path.exists():
            _sample_viol_cache["rows"] = {}
            _sample_viol_cache["mtime"] = 0.0
            return {}
        mtime = csv_path.stat().st_mtime
        if _sample_viol_cache["rows"] and _sample_viol_cache["mtime"] == mtime:
            return _sample_viol_cache["rows"]
        rows: dict[str, dict] = {}
        import csv as _csv
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f)
            for r in reader:
                c = _canon_plate(r.get("plate_text") or r.get("plate") or r.get("Biển Số") or "")
                if c:
                    rows[c] = r
        _sample_viol_cache["rows"] = rows
        _sample_viol_cache["mtime"] = mtime
        return rows
    except Exception:
        return _sample_viol_cache.get("rows") or {}


def _load_reference_plate_sources() -> dict[str, dict]:
    """
    Aggregate reference plates from:
    - sample_violations.csv
    - seed_database.SAMPLE_VIOLATIONS
    - image_processor mock plate list

    These sources are only for lookup/reference. They must never create new
    violation rows or image files automatically.
    """
    cached = _sample_sources_cache.get("rows")
    if cached is not None:
        return cached

    rows: dict[str, dict] = {}

    try:
        for canon, row in (_load_sample_violations() or {}).items():
            merged = dict(row or {})
            merged.setdefault("source", "sample_violations.csv")
            merged.setdefault("plate_text", row.get("plate_text") or row.get("plate") or _format_plate(canon))
            rows[canon] = merged
    except Exception:
        pass

    try:
        from seed_database import SAMPLE_VIOLATIONS as _seed_sample_violations

        for item in _seed_sample_violations or []:
            plate = item.get("plate") or item.get("plate_text") or ""
            canon = _canon_plate(plate)
            if not canon:
                continue
            merged = dict(rows.get(canon) or {})
            merged.update({
                "plate_text": plate or merged.get("plate_text") or _format_plate(canon),
                "vehicle_type": item.get("vehicle_type") or merged.get("vehicle_type") or "",
                "light_state": item.get("light") or merged.get("light_state") or "",
                "speed_kmh": item.get("speed") or merged.get("speed_kmh") or 0,
                "camera_id": item.get("camera") or merged.get("camera_id") or "",
                "source": merged.get("source") or "seed_database.py",
            })
            rows[canon] = merged
    except Exception:
        pass

    try:
        from image_processor import ImageProcessor as _ImageProcessor

        mock = _ImageProcessor()
        if hasattr(mock, "_mock_plate_catalog"):
            for plate in mock._mock_plate_catalog():
                canon = _canon_plate(plate)
                if not canon:
                    continue
                merged = dict(rows.get(canon) or {})
                merged.setdefault("plate_text", plate)
                merged.setdefault("vehicle_type", "")
                merged.setdefault("light_state", "")
                merged.setdefault("speed_kmh", 0)
                merged.setdefault("camera_id", "IMAGE_PROCESSOR")
                merged.setdefault("source", "image_processor.py")
                rows[canon] = merged
    except Exception:
        pass

    try:
        from csv_importer import CSVImporter as _CSVImporter

        importer = _CSVImporter()
        if hasattr(importer, "get_reference_rows"):
            for item in importer.get_reference_rows() or []:
                plate = item.get("plate_text") or item.get("plate") or ""
                canon = _canon_plate(plate)
                if not canon:
                    continue
                merged = dict(rows.get(canon) or {})
                merged.update({
                    "plate_text": plate or merged.get("plate_text") or _format_plate(canon),
                    "vehicle_type": item.get("vehicle_type") or merged.get("vehicle_type") or "",
                    "light_state": item.get("light_state") or merged.get("light_state") or "",
                    "speed_kmh": item.get("speed_kmh") or merged.get("speed_kmh") or 0,
                    "violation_time": item.get("violation_time") or merged.get("violation_time") or "",
                    "camera_id": item.get("camera_id") or merged.get("camera_id") or "",
                    "source": "csv_importer.py",
                })
                rows[canon] = merged
    except Exception:
        pass

    _sample_sources_cache["rows"] = rows
    return rows

def _image_url_exists(url: str) -> bool:
    try:
        if not url:
            return False
        # Support local paths only.
        if url.startswith("/imge/"):
            rel = url[len("/imge/"):]
            p = Path(rel)
            if len(p.parts) >= 2:
                sub = p.parts[0]
                name = "/".join(p.parts[1:])
                if (IMAGE_DIR / sub / name).exists() or (LEGACY_IMAGE_DIR / sub / name).exists():
                    return True
            return (IMAGE_DIR / rel).exists() or (LEGACY_IMAGE_DIR / rel).exists()
        if url.startswith("/static/uploads/"):
            rel = url[len("/static/uploads/"):]
            p = Path(rel)
            if len(p.parts) >= 2:
                sub = p.parts[0]
                name = "/".join(p.parts[1:])
                return (IMAGE_DIR / sub / name).exists() or (LEGACY_IMAGE_DIR / sub / name).exists()
        return False
    except Exception:
        return False


def _safe_plate_filename(plate: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9._-]+", "_", (plate or "").strip().upper())
    cleaned = cleaned.strip("._-")
    return cleaned or "UNKNOWN"


def _save_direct_violation_frame(img_bytes: bytes, plate: str, ts_now: int, suffix: str = "") -> str:
    """Save the raw camera frame at repo-level imge/. No crop, no stamp, no synthetic overlays."""
    if not img_bytes:
        return ""
    try:
        safe = _safe_plate_filename(plate)
        tail = f"_{suffix}" if suffix else ""
        fname = f"{safe}_{ts_now}{tail}.jpg"
        fpath = IMAGE_DIR / fname
        fpath.write_bytes(img_bytes)
        return f"/imge/{fname}"
    except Exception as e:
        log.error("Save direct frame: %s", e)
        return ""

def _make_placeholder_frame_jpg(plate: str, ts: int) -> bytes:
    try:
        ph = np.zeros((480, 640, 3), dtype=np.uint8)
        ph[:] = (12, 18, 30)
        cv2.putText(ph, f"BSX: {plate}", (40, 200),
                    cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 230, 255), 2, cv2.LINE_AA)
        cv2.putText(ph, datetime.fromtimestamp(ts).strftime("%H:%M:%S  %d/%m/%Y"),
                    (40, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 180, 255), 1, cv2.LINE_AA)
        cv2.rectangle(ph, (2, 2), (637, 477), (50, 50, 200), 2)
        _, buf_ph = cv2.imencode(".jpg", ph, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return buf_ph.tobytes()
    except Exception:
        return b""

def _ocr_plate_from_jpg_bytes(image_bytes: bytes) -> tuple[str, float]:
    """
    OCR license plate from an image (best-effort) using EasyOCR.
    Returns (plate_text_formatted, confidence_0_1).
    """
    global _ocr_reader
    try:
        if not image_bytes:
            return "", 0.0
        if _ocr_reader is None:
            try:
                import easyocr as _easyocr
            except Exception:
                _ocr_reader = False
            else:
                _ocr_reader = _easyocr.Reader(["en"], gpu=False)
        if _ocr_reader is False:
            return "", 0.0

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return "", 0.0

        vn_patterns = [
            re.compile(r"^\d{2}[A-Z]\d{4,5}$"),     # 51B12345, 51B1234
            re.compile(r"^\d{2}[A-Z]\d\d{5}$"),     # 49E199966 (legacy with dot)
            re.compile(r"^\d{2}[A-Z]{2}\d{4,5}$"),  # 30AA12345 (rare)
        ]

        def _looks_like_plate(c: str) -> bool:
            if not c:
                return False
            return any(p.match(c) for p in vn_patterns)

        # Try normal + horizontal-flip (in case camera is mirrored by driver/browser).
        best_txt = ""
        best_conf = 0.0
        for cand in (img, cv2.flip(img, 1)):
            results = _ocr_reader.readtext(cand, detail=1, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. ")
            for (_bbox, txt, conf) in results or []:
                c = _canon_plate(txt)
                if len(c) < 6 or not _looks_like_plate(c):
                    continue
                if conf and float(conf) > best_conf:
                    best_conf = float(conf)
                    best_txt = c
        if not best_txt:
            return "", 0.0
        return _format_plate(best_txt), float(best_conf or 0.0)
    except Exception:
        return "", 0.0


def _ocr_plate_from_jpg_bytes_with_bbox(image_bytes: bytes) -> tuple[str, float, list | None]:
    """
    OCR license plate using EasyOCR and also return best bbox (4 points) for cropping.
    Returns (plate_text_formatted, confidence_0_1, bbox_points_or_None).
    """
    global _ocr_reader
    try:
        if not image_bytes:
            return "", 0.0, None
        if _ocr_reader is None:
            try:
                import easyocr as _easyocr
            except Exception:
                _ocr_reader = False
            else:
                _ocr_reader = _easyocr.Reader(["en"], gpu=False)
        if _ocr_reader is False:
            return "", 0.0, None

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img0 = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img0 is None:
            return "", 0.0, None
        h0, w0 = img0.shape[:2]

        vn_patterns = [
            re.compile(r"^\d{2}[A-Z]\d{4,5}$"),
            re.compile(r"^\d{2}[A-Z]\d\d{5}$"),
            re.compile(r"^\d{2}[A-Z]{2}\d{4,5}$"),
        ]

        def _looks_like_plate(c: str) -> bool:
            return bool(c) and any(p.match(c) for p in vn_patterns)

        best_txt = ""
        best_conf = 0.0
        best_bbox = None
        best_flipped = False

        for flipped, cand in ((False, img0), (True, cv2.flip(img0, 1))):
            results = _ocr_reader.readtext(cand, detail=1, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. ")
            for (bbox, txt, conf) in results or []:
                c = _canon_plate(txt)
                if len(c) < 6 or not _looks_like_plate(c):
                    continue
                fc = float(conf or 0.0)
                if fc > best_conf:
                    best_conf = fc
                    best_txt = c
                    best_bbox = bbox
                    best_flipped = flipped

        if not best_txt:
            return "", 0.0, None

        # Normalize bbox to original (non-flipped) coordinates
        if best_bbox and best_flipped:
            try:
                # bbox is 4 points: [[x,y],...]
                best_bbox = [[float(w0) - float(p[0]), float(p[1])] for p in best_bbox]
            except Exception:
                best_bbox = None

        return _format_plate(best_txt), float(best_conf or 0.0), best_bbox
    except Exception:
        return "", 0.0, None


def _get_yolo_model():
    global _yolo_model
    if _yolo_model is False:
        return None
    if _yolo_model is not None:
        return _yolo_model
    try:
        from ultralytics import YOLO as _YOLO
    except Exception:
        _yolo_model = False
        return None
    try:
        model_path = BASE_DIR / "yolov8n.pt"
        if not model_path.exists():
            _yolo_model = False
            return None
        _yolo_model = _YOLO(str(model_path))
        return _yolo_model
    except Exception:
        _yolo_model = False
        return None


def _detect_vehicle_type_from_img(img_bgr) -> tuple[str, float, int]:
    """
    Best-effort vehicle type detection using YOLOv8n (COCO).
    Returns (vehicle_type, best_confidence_0_1, vehicles_count).
    """
    try:
        model = _get_yolo_model()
        if model is None or img_bgr is None:
            return "", 0.0, 0
        # COCO class ids: 2=car, 3=motorcycle, 5=bus, 7=truck
        cls_map = {2: "CAR", 3: "MOTORBIKE", 5: "CAR", 7: "CAR"}
        results = model(img_bgr, verbose=False, conf=0.35, iou=0.50, imgsz=640)
        boxes = results[0].boxes if results else None
        if boxes is None:
            return "", 0.0, 0
        best_type = ""
        best_conf = 0.0
        count = 0
        for box in boxes:
            cls_id = int(box.cls[0].item())
            if cls_id not in cls_map:
                continue
            conf_v = float(box.conf[0].item())
            if conf_v < 0.35:
                continue
            count += 1
            if conf_v > best_conf:
                best_conf = conf_v
                best_type = cls_map[cls_id]
        return best_type, best_conf, count
    except Exception:
        return "", 0.0, 0


def _crop_plate_img_from_bbox(image_bytes: bytes, bbox) -> bytes:
    try:
        if not image_bytes or not bbox:
            return b""
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return b""
        h, w = img.shape[:2]
        xs = [float(p[0]) for p in bbox]
        ys = [float(p[1]) for p in bbox]
        x1, x2 = max(0, int(min(xs))), min(w - 1, int(max(xs)))
        y1, y2 = max(0, int(min(ys))), min(h - 1, int(max(ys)))
        if x2 <= x1 or y2 <= y1:
            return b""
        pad_x = int((x2 - x1) * 0.12) + 6
        pad_y = int((y2 - y1) * 0.18) + 6
        x1 = max(0, x1 - pad_x); x2 = min(w - 1, x2 + pad_x)
        y1 = max(0, y1 - pad_y); y2 = min(h - 1, y2 + pad_y)
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return b""
        _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return buf.tobytes()
    except Exception:
        return b""

# ════════════════════════════════════════════════════════════════
# CAMERA LOCATION CONFIG
# ════════════════════════════════════════════════════════════════
CAM_STATION_ID   = os.getenv("CAM_STATION_ID",   "CAM-HCM-001")
CAM_NAME         = os.getenv("CAM_NAME",          "Camera Giám Sát #1")
CAM_STREET       = os.getenv("CAM_STREET",        "Đường Đinh Bộ Lĩnh")
CAM_INTERSECTION = os.getenv("CAM_INTERSECTION",  "Ngã tư Hàng Xanh")
CAM_DISTRICT     = os.getenv("CAM_DISTRICT",      "Quận Bình Thạnh")
CAM_CITY         = os.getenv("CAM_CITY",          "TP. Hồ Chí Minh")
CAM_DIRECTION    = os.getenv("CAM_DIRECTION",     "Hướng Bắc → Nam")
CAM_LAT          = os.getenv("CAM_LAT",           "10.8037")
CAM_LNG          = os.getenv("CAM_LNG",           "106.7143")

def get_location_info() -> dict:
    return {
        "station_id":   CAM_STATION_ID,
        "cam_name":     CAM_NAME,
        "street":       CAM_STREET,
        "intersection": CAM_INTERSECTION,
        "district":     CAM_DISTRICT,
        "city":         CAM_CITY,
        "direction":    CAM_DIRECTION,
        "lat":          CAM_LAT,
        "lng":          CAM_LNG,
        "full_address": f"{CAM_INTERSECTION}, {CAM_STREET}, {CAM_DISTRICT}, {CAM_CITY}",
    }

# ════════════════════════════════════════════════════════════════
# MQTT CONFIG
# ════════════════════════════════════════════════════════════════
MQTT_HOST           = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT           = int(os.getenv("MQTT_PORT", 1883))
MQTT_KEEPALIVE      = 60
TOPIC_ESP32_STATUS  = "traffic/esp32/status"
TOPIC_ESP32_FRAME   = "traffic/esp32/frame"
TOPIC_AI_VIOLATION  = "traffic/ai/violation"
TOPIC_AI_CONTEXT    = "traffic/ai/context"
TOPIC_TRAFFIC_STATE = "traffic/light/state"
TOPIC_CMD_LIGHT     = "traffic/cmd/light"
TOPIC_CMD_EMERGENCY = "traffic/cmd/emergency"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUNTIME FLAGS â€” simulation + caching
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = str(v).strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default

VIRTUAL_CLUSTER_AUTOSTART = _env_bool("VIRTUAL_CLUSTER_AUTOSTART", True)
ACCEPT_VIRTUAL_VIOLATIONS = _env_bool("ACCEPT_VIRTUAL_VIOLATIONS", False)
IMAGE_CACHE_MAX_AGE_S     = int(os.getenv("IMAGE_CACHE_MAX_AGE_S", "86400"))  # default 24h
IMAGE_CACHE_IMMUTABLE     = _env_bool("IMAGE_CACHE_IMMUTABLE", False)

# ════════════════════════════════════════════════════════════════
# AUTH & THINGSBOARD CONFIG
# ════════════════════════════════════════════════════════════════
TB_HOST          = os.getenv("TB_HOST", "http://localhost:8080")
TB_ACCESS_TOKEN  = os.getenv("TB_TOKEN", "")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "TRAFFIC_AI_TOKEN")

_ADMIN_USER = os.getenv("ADMIN_USER", "admin")
_ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")   # Override via env in production!
_ADMIN_ROLE = "superadmin"
_TOKEN_TTL  = 28_800   # 8 hours

# ════════════════════════════════════════════════════════════════
# 7 GIỚI HẠN NGỮ CẢNH TỐI ƯU ESP32 (CONTEXT_LIMITS)
# ════════════════════════════════════════════════════════════════
CONTEXT_LIMITS = {
    "speed_kmh":        {"max": 20,             "unit": "km/h", "label": "Vận tốc"},
    "vehicles_frame":   {"max": 6,              "unit": "xe",   "label": "Vehicle/khung"},
    "weather":          {"allowed": ["SUN","LIGHT_RAIN","CLOUDY"], "unit":"","label":"Thời tiết"},
    "distance":         {"optimal": 5,          "unit": "m",    "label": "Khoảng cách"},
    "roi":              {"value": "STOP_LINE",   "unit": "",     "label": "Vùng ROI"},
    "capture_interval": {"max": 0.5,            "unit": "s",    "label": "Tốc độ chụp"},
    "target_objects":   {"allowed": ["MOTORBIKE","CAR"],"unit":"","label":"Đối tượng"},
}

CAMERA_OPTIMAL = {
    "frame_size":    "FRAMESIZE_XGA", "jpeg_quality": 8, "fb_count": 2,
    "ae_level":      -2, "gainceiling": "GAINCEILING_4X", "contrast": 1,
    "sharpness":     2,  "denoise": 1,  "xclk_freq_hz": 20_000_000,
}

# ════════════════════════════════════════════════════════════════
# FLASK + SOCKETIO
# ════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "traffic-ai-secret-2026")

# CORS: default "*" for development. Set CORS_ORIGINS env var for production.
# Example: CORS_ORIGINS="https://yourdomain.com,https://admin.yourdomain.com"
_cors_raw = os.getenv("CORS_ORIGINS", "*")
_cors_origins: list | str = [o.strip() for o in _cors_raw.split(",")] if _cors_raw != "*" else "*"

socketio = SocketIO(
    app, cors_allowed_origins=_cors_origins, async_mode="threading",
    logger=False, engineio_logger=False
)

# ════════════════════════════════════════════════════════════════
# GLOBAL STATE
# ════════════════════════════════════════════════════════════════
state_lock = threading.RLock()

traffic_state = {
    "light": "RED", "phase": "ĐỎ", "countdown": 30, "mode": "AUTO",
    "camera": "ACTIVE",
    "cycle": {"green_duration": 30, "yellow_duration": 5, "red_duration": 30},
    "updated_at": int(time.time()),
}

context_state = {
    "speed_kmh": 0.0, "vehicles_frame": 0, "weather": "SUN",
    "distance": 5.0, "capture_interval": 0.5, "roi": "STOP_LINE",
    "target_objects": ["MOTORBIKE", "CAR"],
    "fps": 0, "violations_today": 0, "updated_at": int(time.time()),
    "context_ok": True, "context_errors": [],
}

# Device — khớp 100% với virtual_esp32_cluster.py DEVICES
devices_state = {
    "esp32_cam_1": {"name":"ESP32-CAM #1", "ip":"192.168.1.101", "status":"OFFLINE", "signal":0, "temp":0, "uptime":0, "last_seen":0, "fw":""},
    "esp32_cam_2": {"name":"ESP32-CAM #2", "ip":"192.168.1.102", "status":"OFFLINE", "signal":0, "temp":0, "uptime":0, "last_seen":0, "fw":""},
    "esp32_cam_3": {"name":"ESP32-CAM #3", "ip":"192.168.1.103", "status":"OFFLINE", "signal":0, "temp":0, "uptime":0, "last_seen":0, "fw":""},
    "esp32_main":  {"name":"ESP32 Main",   "ip":"192.168.1.110", "status":"OFFLINE", "signal":0, "temp":0, "uptime":0, "last_seen":0, "fw":""},
    "esp32_led":   {"name":"LED 7 Đoạn",  "ip":"192.168.1.111", "status":"OFFLINE", "signal":0, "temp":0, "uptime":0, "last_seen":0, "fw":""},
}

latest_frame: bytes | None = None
frame_lock   = threading.Lock()

system_stats = {
    "start_time": time.time(), "violations_total": 0, "violations_today": 0,
    "frames_processed": 0, "mqtt_messages": 0, "ai_detections": 0,
}

# ════════════════════════════════════════════════════════════════
# AUTH — Token validation
# ════════════════════════════════════════════════════════════════
def _is_valid_token(token: str) -> bool:
    if not token:
        return False
    token = token.strip()
    if not token:
        return False
    # Accept DASHBOARD_SECRET trực tiếp
    if token == DASHBOARD_SECRET or token.lower() == DASHBOARD_SECRET.lower():
        return True
    # JWT-style legacy token
    if token.startswith("legacy."):
        try:
            parts = base64.b64decode(token[7:]).decode().split(":")
            if len(parts) >= 3 and parts[0] == _ADMIN_USER:
                age = time.time() - int(parts[2]) / 1000
                return 0 <= age < _TOKEN_TTL
        except Exception:
            pass
    return False


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        tok  = auth.removeprefix("Bearer ").strip()
        if not tok:
            tok = request.args.get("token", "").strip()
        if not _is_valid_token(tok):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════════
# DATABASE — Unified schema (tương thích schema.sql + app.py)
# ════════════════════════════════════════════════════════════════
def _init_db():
    """
    Initialize database per schema.sql — create tables if missing.
    Supports columns per schema.sql (plate_text, vehicle_type, violation_ts...)
    và app.py alias (plate, type, ts...) thông qua VIEW.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    c = conn.cursor()

    # ── users table (schema.sql) ──
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT,
        role TEXT NOT NULL DEFAULT 'VIEWER',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── violations table — unified schema ──
    c.execute("""CREATE TABLE IF NOT EXISTS violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        -- License plate info (OCR result)
        plate_text TEXT DEFAULT '',
        plate_confidence REAL DEFAULT 0.0,

        -- Vehicle info
        vehicle_type TEXT DEFAULT 'UNKNOWN',
        vehicle_confidence REAL DEFAULT 0.0,

        -- Violation info
        light_state TEXT NOT NULL DEFAULT 'RED',
        speed_kmh REAL DEFAULT 0.0,
        roi_name TEXT DEFAULT 'STOP_LINE',
        vehicles_frame INTEGER DEFAULT 0,

        -- Image info
        full_image_path TEXT DEFAULT '',
        plate_image_path TEXT DEFAULT '',

        -- Thông tin device
        camera_id TEXT DEFAULT 'CAM_01',
        esp32_id TEXT DEFAULT 'ESP32_MAIN',

        -- Thời gian
        violation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        violation_ts INTEGER,

        -- Trạng thái
        status TEXT DEFAULT 'NEW',
        notes TEXT DEFAULT '',
        edited_by INTEGER,

        -- Địa điểm
        location_name TEXT DEFAULT '',
        location_address TEXT DEFAULT '',
        location_district TEXT DEFAULT '',
        location_city TEXT DEFAULT '',
        location_direction TEXT DEFAULT '',
        lat REAL,
        lng REAL,
        station_id TEXT DEFAULT ''
    )""")

    # Auto-add missing columns for older DBs (schema migration)
    existing = {r[1] for r in c.execute("PRAGMA table_info(violations)").fetchall()}
    new_cols = [
        # Core unified schema columns (needed even when DB already exists with legacy columns)
        ("plate_text",        "TEXT DEFAULT ''"),
        ("plate_confidence",  "REAL DEFAULT 0.0"),
        ("vehicle_type",      "TEXT DEFAULT 'UNKNOWN'"),
        ("full_image_path",   "TEXT DEFAULT ''"),
        ("camera_id",         "TEXT DEFAULT 'CAM_01'"),
        ("violation_time",    "TIMESTAMP"),
        ("violation_ts",      "INTEGER"),
        ("status",            "TEXT DEFAULT 'NEW'"),

        ("vehicles_frame",    "INTEGER DEFAULT 0"),
        ("location_name",     "TEXT DEFAULT ''"),
        ("location_address",  "TEXT DEFAULT ''"),
        ("location_district", "TEXT DEFAULT ''"),
        ("location_city",     "TEXT DEFAULT ''"),
        ("location_direction","TEXT DEFAULT ''"),
        ("lat",               "REAL"),
        ("lng",               "REAL"),
        ("station_id",        "TEXT DEFAULT ''"),
        ("roi_name",          "TEXT DEFAULT 'STOP_LINE'"),
        ("vehicle_confidence","REAL DEFAULT 0.0"),
        ("esp32_id",          "TEXT DEFAULT 'ESP32_MAIN'"),
        ("plate_image_path",  "TEXT DEFAULT ''"),
    ]
    for col, typedef in new_cols:
        if col not in existing:
            try:
                c.execute(f"ALTER TABLE violations ADD COLUMN {col} {typedef}")
            except Exception:
                pass
    # Invalidate column cache so _insert_violation() re-reads the updated schema.
    global _violations_cols_cache
    _violations_cols_cache = None

    # Backfill unified columns from legacy columns when present.
    # Legacy schema observed in older traffic_ai.db: plate/type/image_url/cam_id/ts/confidence/roi.
    existing = {r[1] for r in c.execute("PRAGMA table_info(violations)").fetchall()}
    try:
        if "plate" in existing and "plate_text" in existing:
            c.execute("UPDATE violations SET plate_text = COALESCE(NULLIF(plate_text,''), plate)")
        if "type" in existing and "vehicle_type" in existing:
            c.execute("UPDATE violations SET vehicle_type = COALESCE(NULLIF(vehicle_type,''), type)")
        if "confidence" in existing and "plate_confidence" in existing:
            c.execute("UPDATE violations SET plate_confidence = COALESCE(NULLIF(plate_confidence,0), confidence)")
        if "image_url" in existing and "full_image_path" in existing:
            c.execute("UPDATE violations SET full_image_path = COALESCE(NULLIF(full_image_path,''), image_url)")
        if "cam_id" in existing and "camera_id" in existing:
            c.execute("UPDATE violations SET camera_id = COALESCE(NULLIF(camera_id,''), cam_id)")
        if "ts" in existing and "violation_ts" in existing:
            c.execute("UPDATE violations SET violation_ts = COALESCE(violation_ts, ts)")
        if "violation_ts" in existing and "violation_time" in existing:
            c.execute("UPDATE violations SET violation_time = COALESCE(violation_time, datetime(violation_ts,'unixepoch','localtime'))")
        if "roi" in existing and "roi_name" in existing:
            c.execute("UPDATE violations SET roi_name = COALESCE(NULLIF(roi_name,''), roi)")
        if "status" in existing:
            c.execute("UPDATE violations SET status = COALESCE(NULLIF(status,''), 'NEW')")
    except Exception:
        pass

    # ── device_status table (schema.sql) ──
    c.execute("""CREATE TABLE IF NOT EXISTS device_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE NOT NULL,
        device_name TEXT NOT NULL,
        device_type TEXT NOT NULL,
        is_online INTEGER DEFAULT 0,
        last_heartbeat TIMESTAMP,
        heartbeat_ts INTEGER,
        ip_address TEXT,
        mac_address TEXT,
        firmware_version TEXT,
        signal_strength INTEGER DEFAULT 0,
        cpu_temp_c REAL DEFAULT 0.0,
        uptime_seconds INTEGER DEFAULT 0,
        frames_sent INTEGER DEFAULT 0,
        frames_processed INTEGER DEFAULT 0,
        detections_total INTEGER DEFAULT 0,
        violations_detected INTEGER DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── traffic_state_history table ──
    c.execute("""CREATE TABLE IF NOT EXISTS traffic_state_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        light_state TEXT NOT NULL,
        phase_duration INTEGER NOT NULL,
        mode TEXT DEFAULT 'AUTO',
        triggered_by TEXT,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        changed_ts INTEGER
    )""")

    # ── system_events table (log) ──
    c.execute("""CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL,
        ts INTEGER NOT NULL
    )""")

    # ── context_snapshots table ──
    c.execute("""CREATE TABLE IF NOT EXISTS context_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        speed_kmh REAL, vehicles_frame INTEGER, weather TEXT,
        capture_interval REAL, fps REAL, context_ok INTEGER,
        ts INTEGER NOT NULL
    )""")

    # ── device_telemetry table ──
    c.execute("""CREATE TABLE IF NOT EXISTS device_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        ts INTEGER NOT NULL,
        is_online INTEGER DEFAULT 0,
        rssi INTEGER DEFAULT 0,
        temp_c REAL DEFAULT 0.0,
        uptime_s INTEGER DEFAULT 0,
        latency_ms REAL DEFAULT 0.0,
        last_http_code INTEGER DEFAULT 0,
        upload_ok INTEGER DEFAULT 1,
        signal REAL DEFAULT 0.0,
        temp REAL DEFAULT 0.0,
        uptime INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ONLINE'
    )""")

    # ── system_config table ──
    c.execute("""CREATE TABLE IF NOT EXISTS system_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_key TEXT UNIQUE NOT NULL,
        config_value TEXT,
        config_type TEXT,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_by INTEGER
    )""")

    # ── Indexes ──
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_viol_ts      ON violations(violation_ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_viol_plate   ON violations(plate_text)",
        "CREATE INDEX IF NOT EXISTS idx_viol_light   ON violations(light_state)",
        "CREATE INDEX IF NOT EXISTS idx_viol_camera  ON violations(camera_id)",
        "CREATE INDEX IF NOT EXISTS idx_viol_status  ON violations(status)",
        "CREATE INDEX IF NOT EXISTS idx_events_ts    ON system_events(ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_device_id    ON device_status(device_id)",
    ]
    for idx in indexes:
        try:
            c.execute(idx)
        except Exception:
            pass

    # ── Default system config ──
    configs = [
        ("camera_enabled",     "1",    "BOOLEAN", "Enable camera capture"),
        ("ocr_enabled",        "1",    "BOOLEAN", "Enable OCR reading"),
        ("mqtt_enabled",       "1",    "BOOLEAN", "Enable MQTT communication"),
        ("red_light_duration", "30",   "INTEGER", "Red light phase (seconds)"),
        ("yellow_light_duration","5",  "INTEGER", "Yellow light phase (seconds)"),
        ("green_light_duration","30",  "INTEGER", "Green light phase (seconds)"),
        ("capture_interval_ms","500",  "INTEGER", "Capture interval (ms)"),
        ("ocr_confidence_threshold","0.55","FLOAT","Min OCR confidence"),
        ("violation_cooldown", "3.0",  "FLOAT",   "Violation cooldown (seconds)"),
        ("data_retention_days","30",   "INTEGER", "Data retention (days)"),
        ("camera_address",     "Quận Bình Thạnh, TP.HCM","STRING","Camera address"),
    ]
    for key, val, typ, desc in configs:
        c.execute(
            "INSERT OR IGNORE INTO system_config (config_key,config_value,config_type,description) VALUES (?,?,?,?)",
            (key, val, typ, desc)
        )

    # ── Default admin user ──
    c.execute(
        "INSERT OR IGNORE INTO users (username,password_hash,email,role,is_active) VALUES (?,?,?,?,?)",
        ("admin", "pbkdf2:sha256:admin_hash_placeholder", "admin@traffic.local", "ADMIN", 1)
    )

    conn.commit()
    conn.close()
    log.info("✅ DB ready: %s", DB_PATH)


def get_db():
    """Get SQLite connection in Flask application context."""
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db:
        db.close()


def _db_direct():
    """DB connection outside Flask context (used in threads)."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_violations_cols_cache: set[str] | None = None


def _violations_table_columns(conn: sqlite3.Connection) -> set[str]:
    global _violations_cols_cache
    if _violations_cols_cache is None:
        try:
            _violations_cols_cache = {r[1] for r in conn.execute("PRAGMA table_info(violations)").fetchall()}
        except Exception:
            _violations_cols_cache = set()
    return _violations_cols_cache


def _insert_violation(conn: sqlite3.Connection, row: dict) -> int:
    """
    Insert one violation row while supporting both:
    - unified schema (plate_text, vehicle_type, violation_ts, full_image_path, ...)
    - legacy schema (plate, type, ts, date_str, image_url, cam_id, ...)
    """
    cols_exist = _violations_table_columns(conn)
    cols = [k for k in row.keys() if k in cols_exist]
    if not cols:
        raise RuntimeError("violations table has no matching columns")

    qmarks = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO violations ({', '.join(cols)}) VALUES ({qmarks})"
    cur = conn.cursor()
    cur.execute(sql, [row[c] for c in cols])
    return cur.lastrowid


def _row_to_violation(row) -> dict:
    """
    Chuyển SQLite Row → dict chuẩn cho API.
    Hỗ trợ cả tên cột cũ (plate, type, ts) lẫn mới (plate_text, vehicle_type, violation_ts).

    Trường ảnh trả về:
      image_url       → full_image_path  (ảnh toàn cảnh)
      plate_image_url → plate_image_path (ảnh crop license plate riêng)
      full_image_url  → alias của image_url
    """
    d = dict(row)

    # Alias: plate_text → plate (cho frontend cũ)
    d.setdefault("plate",      d.get("plate_text", ""))
    d.setdefault("type",       d.get("vehicle_type", "UNKNOWN"))
    d.setdefault("ts",         d.get("violation_ts", int(time.time())))
    d.setdefault("cam_id",     d.get("camera_id", ""))
    d.setdefault("cam",        d.get("camera_id", ""))
    d.setdefault("roi",        d.get("roi_name", "STOP_LINE"))
    d.setdefault("light",      d.get("light_state", "RED"))

    # OCR confidence — store 0-1 internally, expose as % for frontend
    raw_conf = d.get("plate_confidence", 0.0) or 0.0
    # If stored as 0-1 range, convert to 0-100 for display
    conf_pct = raw_conf * 100 if raw_conf <= 1.0 else raw_conf
    d["confidence"]      = round(conf_pct, 1)
    d["plate_confidence"]= round(conf_pct, 1)

    # ── Ảnh toàn cảnh (full_image_path) ──
    full_img = d.get("full_image_path", "") or ""
    if full_img and (full_img.startswith("/imge/") or full_img.startswith("/static/uploads/")) and not _image_url_exists(full_img):
        full_img = ""
    d["image_url"]     = full_img
    d["full_image_url"]= full_img

    # ── Ảnh crop license plate (plate_image_path) — tách biệt với ảnh gốc ──
    plate_img = d.get("plate_image_path", "") or ""
    if plate_img and (plate_img.startswith("/imge/") or plate_img.startswith("/static/uploads/")) and not _image_url_exists(plate_img):
        plate_img = ""
    # Fallback: nếu chưa có ảnh license plate riêng, dùng ảnh gốc
    if not plate_img:
        plate_img = full_img
    d["plate_image_url"]= plate_img
    d["plate_url"]      = plate_img

    # Tạo time_str, date_str từ violation_ts
    ts_val = d.get("violation_ts") or 0
    try:
        dt_obj = datetime.fromtimestamp(ts_val) if ts_val else datetime.now()
    except Exception:
        dt_obj = datetime.now()
    weekdays = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"]
    d.setdefault("time_str", dt_obj.strftime("%H:%M:%S"))
    d.setdefault("date_str", dt_obj.strftime("%Y-%m-%d"))
    d.setdefault("date_vn",  f"{weekdays[dt_obj.weekday()]}, {dt_obj.strftime('%d/%m/%Y')}")
    d.setdefault("violation_time_str", dt_obj.strftime("%Y-%m-%d %H:%M:%S"))

    # location dict (cho modal frontend)
    if "location" not in d:
        d["location"] = {
            "name":      d.get("location_name", ""),
            "address":   d.get("location_address", ""),
            "district":  d.get("location_district", ""),
            "city":      d.get("location_city", ""),
            "direction": d.get("location_direction", ""),
            "lat":       d.get("lat", ""),
            "lng":       d.get("lng", ""),
            "station_id":d.get("station_id", ""),
            "maps_url":  (f"https://www.google.com/maps?q={d.get('lat')},{d.get('lng')}"
                          if d.get("lat") and d.get("lng") else ""),
        }

    return d


# ════════════════════════════════════════════════════════════════
# SEED DATABASE — Tự động seed khi database rỗng
# ════════════════════════════════════════════════════════════════
def _seed_if_empty():
    """Auto-seed sample data if DB has no violations."""
    try:
        if os.getenv("TRAFFIC_AI_AUTO_SEED", "0").strip().lower() not in {"1", "true", "yes", "on"}:
            log.info("Auto-seed disabled on boot — chỉ dùng dữ liệu thật hoặc dữ liệu mẫu tra cứu có chủ đích.")
            return
        conn = _db_direct()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM violations")
        count = c.fetchone()[0]

        if count == 0:
            log.info("📊 Database empty — seeding sample data...")
            from datetime import timedelta

            SAMPLE_VIOLATIONS = [
                {"plate": "49-E1 999.66", "vtype": "CAR",       "speed": 15.5, "conf": 0.92, "cam": "CAM_01"},
                {"plate": "29-Y3 036.58", "vtype": "MOTORBIKE", "speed": 18.2, "conf": 0.88, "cam": "CAM_01"},
                {"plate": "70-F1 666.66", "vtype": "CAR",       "speed": 12.8, "conf": 0.95, "cam": "CAM_02"},
                {"plate": "97-H6 301.22", "vtype": "MOTORBIKE", "speed": 20.1, "conf": 0.85, "cam": "CAM_02"},
                {"plate": "59-V2 544.11", "vtype": "CAR",       "speed": 14.3, "conf": 0.91, "cam": "CAM_01"},
                {"plate": "51-G1 654.32", "vtype": "MOTORBIKE", "speed": 19.5, "conf": 0.87, "cam": "CAM_02"},
            ]
            loc = get_location_info()
            now = datetime.now()

            for i, v in enumerate(SAMPLE_VIOLATIONS, 1):
                ts = int((now - timedelta(minutes=i * 5)).timestamp())
                c.execute("""
                    INSERT INTO violations
                    (plate_text, plate_confidence, vehicle_type, light_state,
                     speed_kmh, full_image_path, plate_image_path,
                     camera_id, esp32_id, violation_ts, status,
                     location_name, location_address, location_district,
                     location_city, location_direction, station_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    v["plate"], v["conf"], v["vtype"], "RED",
                    v["speed"],
                    "",
                    "",
                    v["cam"], "ESP32_MAIN", ts, "NEW",
                    loc["intersection"],
                    f"{loc['street']}, {loc['intersection']}",
                    loc["district"], loc["city"], loc["direction"],
                    loc["station_id"]
                ))

            # Seed devices
            SAMPLE_DEVICES = [
                ("esp32_cam_1", "ESP32-CAM #1", "CAMERA",     "192.168.1.101"),
                ("esp32_cam_2", "ESP32-CAM #2", "CAMERA",     "192.168.1.102"),
                ("esp32_cam_3", "ESP32-CAM #3", "CAMERA",     "192.168.1.103"),
                ("esp32_main",  "ESP32 Main",   "ESP32_MAIN", "192.168.1.110"),
                ("esp32_led",   "LED 7 Đoạn",  "LED_7SEG",   "192.168.1.111"),
            ]
            now_ts = int(now.timestamp())
            for did, dname, dtype, dip in SAMPLE_DEVICES:
                c.execute("""
                    INSERT OR REPLACE INTO device_status
                    (device_id, device_name, device_type, is_online, ip_address,
                     heartbeat_ts, signal_strength, cpu_temp_c, uptime_seconds)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (did, dname, dtype, 0, dip, now_ts,
                      80 + (hash(did) % 20), 45 + (hash(did) % 15),
                      3600 + (hash(did) % 86400)))

            conn.commit()
            log.info("✅ Seeded %d sample violations + %d device (metadata only, no generated images)", len(SAMPLE_VIOLATIONS), len(SAMPLE_DEVICES))

        conn.close()
    except Exception as e:
        log.error("_seed_if_empty: %s", e)


# ════════════════════════════════════════════════════════════════
# CONTEXT VALIDATOR — 7 context limits (GH1-GH7)
# ════════════════════════════════════════════════════════════════
def validate_context(ctx: dict) -> tuple:
    errors = []
    if ctx.get("speed_kmh", 0) >= 20:
        errors.append(f"🚗 Vận tốc {ctx['speed_kmh']:.1f}km/h ≥ 20km/h")
    if ctx.get("vehicles_frame", 0) > 6:
        errors.append(f"🚦 {ctx['vehicles_frame']} xe/khung > 6")
    if ctx.get("weather", "SUN") not in ["SUN", "LIGHT_RAIN", "CLOUDY"]:
        errors.append(f"🌧 Thời tiết '{ctx.get('weather')}' không hợp lệ")
    if abs(ctx.get("distance", 5) - 5) > 1:
        errors.append(f"📏 Khoảng cách {ctx.get('distance')}m lệch tối ưu 5m")
    if ctx.get("roi", "STOP_LINE") != "STOP_LINE":
        errors.append("🎯 ROI phải là STOP_LINE")
    if ctx.get("capture_interval", 0.5) > 0.5:
        errors.append(f"📸 Tốc độ chụp {ctx.get('capture_interval')}s > 0.5s")
    if not set(ctx.get("target_objects", [])) & {"MOTORBIKE", "CAR"}:
        errors.append("🎭 Đối tượng không hợp lệ — cần MOTORBIKE hoặc CAR")
    return len(errors) == 0, errors


def _normalize_vehicle_type(vtype: str) -> str:
    """
    Normalize vehicle type from different sources (VN/EN) to one of:
    MOTORBIKE, CAR, UNKNOWN.
    """
    t = (vtype or "").strip().upper()
    if not t:
        return "UNKNOWN"
    if ("XE" in t and ("MAY" in t or "MÁY" in t)) or ("MOTO" in t) or ("MOTOR" in t):
        return "MOTORBIKE"
    if ("O TO" in t) or ("Ô TÔ" in t) or ("OTO" in t) or ("CAR" in t) or ("AUTO" in t):
        return "CAR"
    if t in {"MOTORBIKE", "CAR"}:
        return t
    return "UNKNOWN"


# ════════════════════════════════════════════════════════════════
# TRAFFIC CYCLE WORKER
# ════════════════════════════════════════════════════════════════
TRAFFIC_CYCLE = [
    ("GREEN",  "XANH", "IDLE",   1),
    ("YELLOW", "VÀNG", "WARMUP", 2),
    ("RED",    "ĐỎ",   "ACTIVE", 0),
]
_cycle_idx  = 2  # Start with RED light
_cycle_stop = threading.Event()


def _dur(light: str) -> int:
    with state_lock:
        c = traffic_state["cycle"]
        return {"GREEN": c["green_duration"], "YELLOW": c["yellow_duration"],
                "RED": c["red_duration"]}.get(light, 30)


def _emit_traffic():
    with state_lock:
        p = dict(traffic_state)
    socketio.emit("traffic_state", p)
    # Broadcast state to virtual cluster (MQTT or direct-mode) so LED/countdown stay in sync.
    mqtt_publish(TOPIC_TRAFFIC_STATE, {
        "light": p.get("light"),
        "countdown": int(p.get("countdown", 0) or 0),
        "mode": p.get("mode", "AUTO"),
    })


def _traffic_cycle_worker():
    global _cycle_idx
    log.info("🚦 Traffic cycle started")
    while not _cycle_stop.is_set():
        with state_lock:
            if traffic_state["mode"] == "EMERGENCY":
                if traffic_state["countdown"] > 0:
                    traffic_state["countdown"] -= 1
                traffic_state["updated_at"] = int(time.time())
                # Release lock BEFORE emitting and sleeping so other threads
                # (API requests, MQTT handler) are not blocked for 1 full second.
                # We snapshot the state we need to emit before releasing.
                _snapshot_for_emit = True
            else:
                _snapshot_for_emit = False

        # EMERGENCY: emit and sleep OUTSIDE the lock to avoid starving other threads.
        if _snapshot_for_emit:
            _emit_traffic()
            time.sleep(1)
            continue

        with state_lock:
            traffic_state["countdown"] -= 1
            if traffic_state["countdown"] <= 0:
                _, _, _, ni = TRAFFIC_CYCLE[_cycle_idx]
                _cycle_idx = ni
                l, p, cam, _ = TRAFFIC_CYCLE[_cycle_idx]
                traffic_state.update({
                    "light": l, "phase": p, "camera": cam,
                    "countdown": _dur(l), "updated_at": int(time.time())
                })
                # Log traffic light change to DB
                _log_traffic_change(l, _dur(l))
            else:
                traffic_state["updated_at"] = int(time.time())

        _emit_traffic()
        time.sleep(1)


def _log_traffic_change(light: str, duration: int):
    try:
        conn = _db_direct()
        conn.execute(
            "INSERT INTO traffic_state_history (light_state,phase_duration,mode,triggered_by,changed_ts) VALUES (?,?,?,?,?)",
            (light, duration, "AUTO", "SYSTEM", int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def force_light(light: str, mode: str = "EMERGENCY"):
    global _cycle_idx
    idx = {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(light.upper(), 2)
    l, p, cam, _ = TRAFFIC_CYCLE[idx]
    with state_lock:
        _cycle_idx = idx
        traffic_state.update({
            "light": l, "phase": p, "camera": cam, "mode": mode,
            "countdown": _dur(l), "updated_at": int(time.time())
        })
    _emit_traffic()
    mqtt_publish(TOPIC_CMD_LIGHT, {"light": l, "mode": mode})
    if mode == "EMERGENCY":
        mqtt_publish(TOPIC_CMD_EMERGENCY, {"active": True, "light": l})
    _log_traffic_change(l, _dur(l))


def reset_auto():
    with state_lock:
        traffic_state.update({"mode": "AUTO", "updated_at": int(time.time())})
    _emit_traffic()
    mqtt_publish(TOPIC_CMD_EMERGENCY, {"active": False})


# ════════════════════════════════════════════════════════════════
# VIOLATION PROCESSING — Handle violations from all sources
# ════════════════════════════════════════════════════════════════
def _stamp_violation_image(img_bytes: bytes, plate: str, vtype: str,
                            speed: float, light: str, ts: int) -> bytes:
    """Stamp violation info watermark onto image."""
    try:
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return img_bytes

        h, w = img.shape[:2]
        loc  = get_location_info()
        dt   = datetime.fromtimestamp(ts)
        weekdays = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"]
        time_str = dt.strftime("%H:%M:%S")
        date_str = f"{weekdays[dt.weekday()]}, {dt.strftime('%d/%m/%Y')}"
        light_color = (0, 0, 220) if light == "RED" else (0, 200, 0)
        light_vn    = "ĐÈN ĐỎ — VI PHẠM" if light == "RED" else light

        banner_h = min(int(h * 0.28), 180)
        overlay  = img.copy()
        cv2.rectangle(overlay, (0, h - banner_h), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.72, img, 0.28, 0, img)
        cv2.rectangle(img, (0, h - banner_h), (w, h - banner_h + 4), light_color, -1)

        FONT  = cv2.FONT_HERSHEY_DUPLEX
        sc    = max(0.38, min(0.65, w / 1200))
        sc_sm = max(0.30, min(0.50, w / 1400))
        thick = max(1, int(sc * 2))
        lh    = int(banner_h / 5.5)
        y0    = h - banner_h + lh + 4

        def put(text, y, scale=None, color=(220, 220, 220), bold=False):
            s = scale or sc
            t = 2 if bold else thick
            cv2.putText(img, text, (10, y), FONT, s, (0, 0, 0), t + 2, cv2.LINE_AA)
            cv2.putText(img, text, (10, y), FONT, s, color,     t,     cv2.LINE_AA)

        def put_r(text, y, scale=None, color=(180, 180, 180)):
            s = scale or sc_sm
            sz = cv2.getTextSize(text, FONT, s, thick)
            x  = w - sz[0][0] - 12
            cv2.putText(img, text, (x, y), FONT, s, (0, 0, 0), thick + 2, cv2.LINE_AA)
            cv2.putText(img, text, (x, y), FONT, s, color,     thick,     cv2.LINE_AA)

        vtype_vn = {"MOTORBIKE": "XE MÁY", "CAR": "Ô TÔ"}.get(vtype, vtype)
        put(f"BSX: {plate}   {vtype_vn}", y0, scale=sc * 1.1, color=(0, 230, 255), bold=True)
        put_r(f"{loc['station_id']}", y0, color=(120, 200, 120))
        put(f"{loc['intersection']}, {loc['street']}", y0 + lh, color=(200, 200, 200))
        put_r(f"{loc['direction']}", y0 + lh, color=(160, 200, 255))
        put(f"{loc['district']}, {loc['city']}", y0 + lh*2, scale=sc_sm, color=(170, 170, 170))
        put_r(f"GPS: {loc['lat']}, {loc['lng']}", y0 + lh*2, color=(130, 180, 130))
        put(f"{time_str}   {date_str}", y0 + lh*3, color=(0, 220, 180))
        put_r(f"Tốc độ: {speed:.1f} km/h", y0 + lh*3, color=(255, 180, 80))
        put(f"VI PHẠM: {light_vn}", y0 + lh*4, scale=sc_sm, color=light_color, bold=True)
        put_r(loc["cam_name"], y0 + lh*4, color=(150, 150, 150))
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), light_color, 3)

        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes()
    except Exception as e:
        log.error("stamp_violation_image: %s", e)
        return img_bytes


def process_violation(payload: dict, _force_process: bool = False):
    """
    Process violations from all sources:
    - MQTT (virtual_esp32_cluster.py publishes traffic/ai/violation)
    - Laptop Camera snapshot
    - API inject (test)
    - POST /api/upload-violation (real IP camera)
    - image_processor.py

    Luồng xử lý:
    1. Check light == RED
    2. Read payload (hỗ trợ cả and legacy format và mới)
    3. Lưu ảnh gốc thật → /imge/<plate>_<ts>.jpg
    4. Không tạo ảnh crop/placeholder riêng
    5. Insert DB (violations)
    6. Emit SocketIO → Dashboard realtime
    """
    with state_lock:
        light = traffic_state["light"]
    # _force_process=True bypasses the RED-light gate for API/upload/inject callers
    # so they don't need to temporarily mutate the global traffic_state.
    if light != "RED" and not _force_process:
        return

    # Enforce GH1–GH7 at server side as a safety net (even if AI/ESP32 already filters).
    # Merge runtime context with payload hints when present.
    # IMPORTANT: When _force_process=True (admin API upload / inject), the GH1-GH7 context
    # limits do NOT apply — those limits govern live ESP32 capture conditions, not admin uploads.
    # Skipping context validation for _force_process ensures admin can always record a violation
    # regardless of the current sensor readings (e.g. speed_kmh > 20 during heavy traffic).
    with state_lock:
        ctx = dict(context_state)
    for k in ("speed_kmh", "vehicles_frame", "weather", "distance", "capture_interval", "roi", "target_objects"):
        if k in payload and payload.get(k) is not None:
            ctx[k] = payload.get(k)
    if not _force_process:
        ok_ctx, _errs = validate_context(ctx)
        if not ok_ctx:
            return

    # Read payload — supports both new format (plate_text) và cũ (plate)
    plate  = (payload.get("plate_text") or payload.get("plate") or "").strip().upper()
    vtype_raw  = payload.get("vehicle_type") or payload.get("type") or "UNKNOWN"
    vtype_norm = _normalize_vehicle_type(vtype_raw)
    if vtype_norm not in {"MOTORBIKE", "CAR"}:
        return
    vtype = vtype_norm
    speed  = float(payload.get("speed_kmh", 0))
    conf   = float(payload.get("plate_confidence") or payload.get("confidence") or 0)
    # OCR Level: normalize confidence to 0-1
    if conf > 1.0:
        conf = conf / 100.0

    # Base64 ảnh gốc (full frame)
    b64_full  = payload.get("image_b64") or payload.get("full_image_b64") or ""
    # Base64 ảnh crop license plate (nếu có, từ AI engine)
    b64_plate = payload.get("plate_image_b64") or payload.get("plate_b64") or ""

    cam    = payload.get("camera_id") or payload.get("cam_id") or "CAM_01"
    esp_id = payload.get("esp32_id") or "ESP32_MAIN"
    roi    = payload.get("roi") or payload.get("roi_name") or "STOP_LINE"
    if str(roi).upper() != "STOP_LINE":
        return
    veh    = int(payload.get("vehicles_frame", 0))

    # OCR Level 1: plate text readable | Level 2: unreadable
    if not plate:
        plate = "UNKNOWN"   # Level 2: weak OCR — admin reviews image and corrects manually

    loc = get_location_info()
    ts  = int(payload.get("ts", time.time()))
    dt  = datetime.fromtimestamp(ts)
    weekdays = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"]
    time_str = dt.strftime("%H:%M:%S")
    date_str = dt.strftime("%Y-%m-%d")
    date_vn  = f"{weekdays[dt.weekday()]}, {dt.strftime('%d/%m/%Y')}"

    # ── Save full-scene violation image ──────────────────────────────
    # Priority: b64_full > pre-existing payload image_url
    image_url = payload.get("image_url") or payload.get("full_image_path") or ""
    # If payload points to a local URL that doesn't exist, ignore it to avoid 404 spam.
    if image_url and (image_url.startswith("/imge/") or image_url.startswith("/static/uploads/")) and not _image_url_exists(image_url):
        image_url = ""
    if b64_full and not image_url:
        try:
            raw     = base64.b64decode(b64_full)
            image_url = _save_direct_violation_frame(raw, plate, ts)
        except Exception as e:
            log.error("Lưu ảnh violations (full): %s", e)

    if not image_url:
        log.info("Bỏ qua tạo placeholder cho %s — hệ thống chỉ lưu ảnh chụp thật.", plate)

    # ── Save cropped plate image ────────────────────────────────────
    plate_url = image_url

    # Write to DB
    try:
        conn = _db_direct()

        # Prepare a superset row for both unified + legacy schemas.
        row = {
            # Unified schema
            "plate_text":        plate,
            "plate_confidence":  conf,
            "vehicle_type":      vtype,
            "light_state":       light,
            "speed_kmh":         speed,
            "roi_name":          roi,
            "vehicles_frame":    veh,
            "full_image_path":   image_url,
            "plate_image_path":  plate_url,
            "camera_id":         cam,
            "esp32_id":          esp_id,
            "violation_ts":      ts,
            "violation_time":    dt.strftime("%Y-%m-%d %H:%M:%S"),
            "status":            "NEW",
            "notes":             "",
            "location_name":     loc["intersection"],
            "location_address":  f"{loc['street']}, {loc['intersection']}",
            "location_district": loc["district"],
            "location_city":     loc["city"],
            "location_direction":loc["direction"],
            "lat":               float(loc.get("lat", 0) or 0),
            "lng":               float(loc.get("lng", 0) or 0),
            "station_id":        loc["station_id"],

            # Legacy schema (some older DBs have NOT NULL constraints here)
            "plate":             plate,
            "type":              vtype,
            "confidence":        round(conf * 100 if conf <= 1.0 else conf, 1),
            "image_url":         image_url,
            "cam_id":            cam,
            "ts":                ts,
            "date_str":          date_str,
            "roi":               roi,
            "processed":         1,
        }

        row_id = _insert_violation(conn, row)
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("DB insert violations: %s", e)
        return

    with state_lock:
        system_stats["violations_total"] += 1
        system_stats["violations_today"] += 1
        context_state["violations_today"] = system_stats["violations_today"]

    conf_pct = round(conf * 100 if conf <= 1.0 else conf, 1)

    # Emit SocketIO → Dashboard realtime
    ev = {
        "id": row_id, "plate": plate, "plate_text": plate,
        "type": vtype, "vehicle_type": vtype,
        "speed_kmh": speed, "light": light, "light_state": light,
        "roi": roi, "vehicles_frame": veh,
        "confidence": conf_pct, "plate_confidence": conf_pct,
        # ── Ảnh: 2 trường riêng biệt ──
        "image_url":        image_url,          # ảnh toàn cảnh
        "full_image_url":   image_url,          # alias
        "full_image_path":  image_url,
        "plate_image_url":  plate_url,          # ảnh crop license plate
        "plate_image_path": plate_url,
        "plate_url":        plate_url,
        # ──────────────────────────────
        "cam_id": cam, "cam": cam, "camera_id": cam,
        "ts": ts, "violation_ts": ts,
        "date_str": date_str, "time_str": time_str, "date_vn": date_vn,
        "violation_time_str": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "NEW",
        "location": {
            "name":      loc["intersection"],
            "address":   f"{loc['street']}, {loc['intersection']}",
            "district":  loc["district"],
            "city":      loc["city"],
            "direction": loc["direction"],
            "lat":       loc["lat"],
            "lng":       loc["lng"],
            "station_id":loc["station_id"],
            "cam_name":  loc["cam_name"],
            "full":      loc["full_address"],
            "maps_url":  f"https://www.google.com/maps?q={loc['lat']},{loc['lng']}",
        },
    }
    socketio.emit("new_violation", ev)
    log.info("🚨 Violation #%d: %s | %s | %.1fkm/h | img=%s | plate_img=%s",
             row_id, plate, vtype, speed, image_url or "none", plate_url or "none")
    _log_event("WARN", "AI",
        f"Violation #{row_id}: {plate} ({vtype}) @ {speed:.1f}km/h | "
        f"{loc['intersection']}, {loc['district']} | {time_str} {date_vn}")

    if TB_ACCESS_TOKEN:
        _push_thingsboard(ev)


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _log_event(level: str, source: str, message: str):
    ts = int(time.time())
    try:
        conn = _db_direct()
        conn.execute(
            "INSERT INTO system_events(level,source,message,ts) VALUES(?,?,?,?)",
            (level, source, message, ts)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    socketio.emit("system_event", {"level": level, "source": source, "message": message, "ts": ts})


def _push_thingsboard(data: dict):
    def _s():
        try:
            requests.post(
                f"{TB_HOST}/api/v1/{TB_ACCESS_TOKEN}/telemetry",
                json=data, timeout=3
            )
        except Exception:
            pass
    threading.Thread(target=_s, daemon=True).start()


# ════════════════════════════════════════════════════════════════
# MQTT CLIENT
# ════════════════════════════════════════════════════════════════
_mqtt_client = None


def mqtt_publish(topic: str, payload):
    """
    Publish to real MQTT (if connected) AND local in-process subscribers (direct-mode cluster).
    `payload` can be dict/str/bytes.
    """
    if isinstance(payload, (dict, list)):
        data_bytes = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        data_bytes = payload.encode("utf-8")
    else:
        data_bytes = payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode("utf-8")

    # Real broker
    try:
        if _mqtt_client and _mqtt_client.is_connected():
            _mqtt_client.publish(topic, data_bytes, qos=1)
    except Exception:
        pass

    # Local bus (no external broker required)
    try:
        for cb in list(_local_mqtt_subscribers):
            try:
                cb(topic, data_bytes)
            except Exception:
                pass
    except NameError:
        # defined later during module import
        pass


_local_mqtt_subscribers: list = []


def mqtt_subscribe_local(callback):
    """Register a local MQTT-like subscriber: callback(topic:str, payload_bytes:bytes)."""
    if callback and callback not in _local_mqtt_subscribers:
        _local_mqtt_subscribers.append(callback)


def mqtt_unsubscribe_local(callback):
    try:
        _local_mqtt_subscribers.remove(callback)
    except ValueError:
        pass


def mqtt_inject(topic: str, payload_bytes: bytes):
    """Inject a message directly into the MQTT handler (used by direct-mode virtual cluster)."""
    class _Msg:
        def __init__(self, t, p):
            self.topic = t
            self.payload = p
    try:
        _on_mqtt_message(None, None, _Msg(topic, payload_bytes))
    except Exception:
        pass


def _on_mqtt_message(client, userdata, msg):
    global latest_frame
    with state_lock:
        system_stats["mqtt_messages"] += 1

    try:
        # Frame stream from ESP32-CAM
        if msg.topic == TOPIC_ESP32_FRAME:
            pl = msg.payload
            with frame_lock:
                latest_frame = base64.b64decode(pl) if pl[:2] == b"//" else bytes(pl)
            with state_lock:
                system_stats["frames_processed"] += 1
            return

        d = json.loads(msg.payload.decode())

        # Trạng thái device (heartbeat)
        if msg.topic == TOPIC_ESP32_STATUS:
            dev = d.get("device_id", "")
            if dev in devices_state:
                with state_lock:
                    devices_state[dev].update({
                        "status":    "ONLINE",
                        "signal":    d.get("rssi", 0),
                        "temp":      d.get("temp", 0),
                        "uptime":    d.get("uptime", 0),
                        "last_seen": int(time.time()),
                        "fw":        d.get("fw", ""),
                    })
                socketio.emit("device_update", {"device_id": dev, **devices_state[dev]})
                # Update device_status DB
                try:
                    conn = _db_direct()
                    conn.execute("""
                        INSERT OR REPLACE INTO device_status
                        (device_id, device_name, device_type, is_online, heartbeat_ts,
                         signal_strength, cpu_temp_c, uptime_seconds, ip_address, firmware_version)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        dev,
                        devices_state[dev]["name"],
                        "CAMERA" if "cam" in dev else ("LED_7SEG" if "led" in dev else "ESP32_MAIN"),
                        1, int(time.time()),
                        d.get("rssi", 0), d.get("temp", 0), d.get("uptime", 0),
                        devices_state[dev].get("ip", ""),
                        d.get("fw", "")
                    ))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    log.debug("Device DB update: %s", e)

                # Save timestamped telemetry (for ThingsBoard/analytics)
                try:
                    conn = _db_direct()
                    conn.execute("""
                        INSERT INTO device_telemetry
                        (device_id,ts,is_online,rssi,temp_c,uptime_s,latency_ms,last_http_code,upload_ok)
                        VALUES(?,?,?,?,?,?,?,?,?)
                    """, (
                        dev,
                        int(time.time()),
                        1,
                        int(d.get("rssi", 0) or 0),
                        float(d.get("temp", 0) or 0),
                        int(d.get("uptime", 0) or 0),
                        float(d.get("latency_ms", 0) or 0),
                        int(d.get("last_http_code", 0) or 0),
                        int(d.get("upload_ok", 1) or 0),
                    ))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

                # ThingsBoard telemetry (single device token) — push compact status payload
                if TB_ACCESS_TOKEN:
                    tb = {
                        "device_id": dev,
                        "device_name": devices_state[dev].get("name", dev),
                        "status": devices_state[dev].get("status", "ONLINE"),
                        "active": True,
                        "Wifi_Status": int(d.get("rssi", 0) or 0),
                        "latency_ms": float(d.get("latency_ms", 0) or 0),
                        "last_http_code": int(d.get("last_http_code", 0) or 0),
                        "upload_ok": int(d.get("upload_ok", 1) or 0),
                        "cpu_temp_c": float(d.get("temp", 0) or 0),
                        "uptime_s": int(d.get("uptime", 0) or 0),
                        "fw_version": str(d.get("fw", "") or ""),
                        "lastActivityTime": int(time.time() * 1000),
                    }
                    _push_thingsboard(tb)

        # Violations from virtual_esp32_cluster.py
        elif msg.topic == TOPIC_AI_VIOLATION:
            if not ACCEPT_VIRTUAL_VIOLATIONS:
                cam_hint = str(d.get("cam_id") or d.get("camera_id") or d.get("device_id") or "")
                # virtual_esp32_cluster.py uses cam_id like: "esp32_cam_1", "esp32_cam_2"...
                if cam_hint.startswith("esp32_cam_"):
                    return
            threading.Thread(target=process_violation, args=(d,), daemon=True).start()

        # Context data from cluster
        elif msg.topic == TOPIC_AI_CONTEXT:
            with state_lock:
                context_state.update({
                    "speed_kmh":       float(d.get("speed_kmh", 0)),
                    "vehicles_frame":  int(d.get("vehicles_frame", 0)),
                    "weather":         d.get("weather", "SUN"),
                    "distance":        float(d.get("distance", 5)),
                    "capture_interval":float(d.get("capture_interval", 0.5)),
                    "roi":             d.get("roi", "STOP_LINE"),
                    "target_objects":  d.get("target_objects", ["MOTORBIKE", "CAR"]),
                    "fps":             float(d.get("fps", 0)),
                    "updated_at":      int(time.time()),
                })
                ok, errs = validate_context(context_state)
                context_state["context_ok"]     = ok
                context_state["context_errors"] = errs
                ctx = dict(context_state)
            socketio.emit("context_update", ctx)

        # traffic/light/state is produced by app.py (controller-of-truth) — ignore if received.
        elif msg.topic == TOPIC_TRAFFIC_STATE:
            return

    except Exception as e:
        log.error("MQTT msg [%s]: %s", msg.topic, e)


def _init_mqtt():
    global _mqtt_client
    try:
        try:
            c = mqtt.Client(
                client_id=f"TrafficAI-{int(time.time())}",
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )
            def _on_conn(client, userdata, flags, reason_code, properties):
                if reason_code.is_failure:
                    log.warning("MQTT connected thất bại: %s", reason_code)
                    return
                log.info("✅ MQTT connected %s:%d", MQTT_HOST, MQTT_PORT)
                client.subscribe([
                    (TOPIC_ESP32_STATUS,  1), (TOPIC_ESP32_FRAME,   0),
                    (TOPIC_AI_VIOLATION,  1), (TOPIC_AI_CONTEXT,    1),
                ])
                _log_event("INFO", "MQTT", f"Kết nối {MQTT_HOST}:{MQTT_PORT}")
            def _on_disc(client, userdata, disconnect_flags, reason_code, properties):
                log.warning("MQTT ngắt connected: %s", reason_code)
            c.on_connect    = _on_conn
            c.on_disconnect = _on_disc
        except AttributeError:
            c = mqtt.Client(client_id=f"TrafficAI-{int(time.time())}")
            def _on_conn_v1(client, userdata, flags, rc):
                if rc == 0:
                    log.info("✅ MQTT connected %s:%d", MQTT_HOST, MQTT_PORT)
                    client.subscribe([
                        (TOPIC_ESP32_STATUS,  1), (TOPIC_ESP32_FRAME,   0),
                        (TOPIC_AI_VIOLATION,  1), (TOPIC_AI_CONTEXT,    1),
                    ])
            c.on_connect = _on_conn_v1
        c.on_message = _on_mqtt_message
        c.reconnect_delay_set(min_delay=2, max_delay=30)
        c.connect_async(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
        c.loop_start()
        _mqtt_client = c
        log.info("📡 MQTT async → %s:%d", MQTT_HOST, MQTT_PORT)
    except Exception as e:
        log.warning("MQTT init (broker offline?): %s — hệ thống tiếp tục", e)


# ════════════════════════════════════════════════════════════════
# LAPTOP CAMERA MODULE v7.0
# ════════════════════════════════════════════════════════════════
_laptop_cam_active   = False
_laptop_cam_thread: threading.Thread | None  = None
_laptop_frame: bytes | None         = None
_laptop_frame_raw: bytes | None     = None
_laptop_frame_lock   = threading.Lock()
_laptop_cam_lock     = threading.Lock()
_laptop_cam_stop_evt: threading.Event | None = None
_laptop_flip_display = False
_LAPTOP_W, _LAPTOP_H = 1024, 768


def _draw_overlay(frame: np.ndarray) -> np.ndarray:
    """Vẽ overlay thông tin lên frame camera."""
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, 30), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.65, frame, 0.35, 0, frame)

    ts_str = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
    cv2.putText(frame, ts_str, (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 230, 255), 1, cv2.LINE_AA)

    with state_lock:
        light   = traffic_state["light"]
        cam_st  = traffic_state["camera"]
        cntdown = traffic_state["countdown"]
        veh     = context_state["vehicles_frame"]
        spd     = context_state["speed_kmh"]

    lc = {"RED": (0,0,220), "YELLOW": (0,200,220), "GREEN": (0,200,80)}.get(light, (80,80,80))
    cv2.circle(frame, (w - 22, 15), 12, lc, -1)
    cv2.circle(frame, (w - 22, 15), 12, (255, 255, 255), 1)
    lv = {"RED": "ĐỎ", "YELLOW": "VÀNG", "GREEN": "XANH"}.get(light, light)
    cv2.putText(frame, f"CAM:{cam_st}  {lv} {cntdown}s",
                (w - 270, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 230, 255), 1, cv2.LINE_AA)

    roi_y = int(h * 0.72)
    cv2.line(frame, (int(w * 0.04), roi_y), (int(w * 0.96), roi_y), (50, 50, 220), 2)
    cv2.putText(frame, "VACH DUNG - ROI - STOP LINE",
                (int(w * 0.24), roi_y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (100, 100, 255), 1, cv2.LINE_AA)

    mc = {"ACTIVE": (0,40,180), "WARMUP": (0,140,200), "IDLE": (40,40,40)}.get(cam_st, (40,40,40))
    cv2.rectangle(frame, (5, h - 26), (195, h - 4), mc, -1)
    cv2.putText(frame, f"LAPTOP CAM  {cam_st}",
                (9, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"Xe:{veh}  Speed:{spd:.1f}km/h",
                (w - 270, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (160, 210, 255), 1, cv2.LINE_AA)
    return frame


def _laptop_cam_worker(stop_event: threading.Event):
    """Laptop camera worker — straight frame (no flip) for accurate OCR."""
    global _laptop_frame, _laptop_frame_raw, _laptop_cam_active
    log.info("🎥 Laptop camera v7.0 started — straight frame for OCR")

    cap = None
    for attempt in range(3):
        if stop_event.is_set():
            _laptop_cam_active = False
            return
        c = cv2.VideoCapture(0)
        if c.isOpened():
            cap = c
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  _LAPTOP_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _LAPTOP_H)
            cap.set(cv2.CAP_PROP_FPS, 30)
            log.info("✅ Webcam opened %dx%d (attempt %d)", _LAPTOP_W, _LAPTOP_H, attempt + 1)
            break
        else:
            c.release()
            log.warning("⚠️  Webcam thử attempt %d/3 thất bại — retrying in 0.5s", attempt + 1)
            time.sleep(0.5)

    if cap is None:
        log.warning("⚠️  No webcam available — laptop camera module stays offline")
        _laptop_cam_active = False
        with _laptop_frame_lock:
            _laptop_frame = None
            _laptop_frame_raw = None
        return

    _laptop_cam_active = True
    fidx = 0
    _last_capture_ts = 0.0
    CAPTURE_COOLDOWN = 3.0   # GH6: 3s cooldown giữa các attempt ghi violations
    VEHICLE_CLASSES  = {2: "CAR", 3: "MOTORBIKE", 5: "CAR", 7: "CAR"}

    while not stop_event.is_set():
        if cap and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
        else:
            break

        frame_with_overlay = _draw_overlay(frame.copy())
        ok_raw, buf_raw = cv2.imencode(".jpg", frame_with_overlay, [cv2.IMWRITE_JPEG_QUALITY, 82])

        frame_display = cv2.flip(frame_with_overlay, 1) if _laptop_flip_display else frame_with_overlay
        ok, buf = cv2.imencode(".jpg", frame_display, [cv2.IMWRITE_JPEG_QUALITY, 82])

        with _laptop_frame_lock:
            if ok:
                _laptop_frame = buf.tobytes()
            if ok_raw:
                _laptop_frame_raw = buf_raw.tobytes()

        # Auto-detect violations when light is RED
        now = time.time()
        with state_lock:
            cur_light = traffic_state["light"]

        if cur_light == "RED" and (now - _last_capture_ts) > CAPTURE_COOLDOWN:
            try:
                from ai_engine import start_ai as _ai_start
                # YOLO detect nếu có model
                try:
                    from ultralytics import YOLO as _YOLO
                    yolo_model = getattr(_laptop_cam_worker, "_yolo_model", None)
                    if yolo_model is None:
                        model_path = BASE_DIR / "yolov8n.pt"
                        if model_path.exists():
                            _laptop_cam_worker._yolo_model = _YOLO(str(model_path))
                            yolo_model = _laptop_cam_worker._yolo_model
                    if yolo_model is not None and ok_raw:
                        results = yolo_model(frame, verbose=False, conf=0.40, iou=0.50, imgsz=640)
                        boxes   = results[0].boxes if results else None
                        detected_vehicles = []
                        if boxes is not None:
                            for box in boxes:
                                cls_id = int(box.cls[0].item())
                                conf_v = float(box.conf[0].item())
                                if cls_id in VEHICLE_CLASSES and conf_v > 0.40:
                                    x1,y1,x2,y2 = [int(v) for v in box.xyxy[0].tolist()]
                                    detected_vehicles.append({
                                        "type": VEHICLE_CLASSES[cls_id],
                                        "conf": conf_v, "bbox": (x1,y1,x2,y2)
                                    })
                        if detected_vehicles:
                            best = max(detected_vehicles, key=lambda v: v["conf"])
                            vtype = best["type"]
                            speed_est = float(context_state.get("speed_kmh", 14.5))
                            ts_cap = int(now)
                            raw_bytes = buf_raw.tobytes()
                            log.debug("Auto-capture disabled: waiting for manual snapshot with real OCR plate.")
                except (ImportError, Exception) as e:
                    log.debug("YOLO auto-detect skip: %s", e)
            except Exception as e:
                log.debug("Auto-capture skip: %s", e)

        time.sleep(0.04)

    if cap:
        cap.release()
        log.info("📷 VideoCapture(0) đã đóng")
    _laptop_cam_active = False
    log.info("🛑 Laptop camera worker dừng")


def _gen_laptop_frames():
    """Stream MJPEG từ laptop camera."""
    while True:
        with _laptop_frame_lock:
            frame = _laptop_frame
        if frame is None:
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            img[:] = (8, 13, 24)
            cv2.putText(img, "Camera chua khoi dong", (110, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, (40, 100, 200), 2)
            cv2.putText(img, "Nhan BAT CAMERA de bat dau", (90, 268),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 80, 120), 1)
            _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame = buf.tobytes()
            time.sleep(0.2)
        else:
            time.sleep(0.04)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


def _gen_esp32_frames():
    """Stream MJPEG từ ESP32-CAM qua MQTT."""
    while True:
        with frame_lock:
            frame = latest_frame
        if frame is None:
            img = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(img, "Waiting for ESP32-CAM...", (100, 170),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
            cv2.putText(img, datetime.now().strftime("%H:%M:%S"), (260, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 1)
            with state_lock:
                light = traffic_state["light"]
            cv2.circle(img, (320, 290), 18,
                       {"RED": (0,0,220), "YELLOW": (0,200,220), "GREEN": (0,220,0)}.get(light, (80,80,80)), -1)
            _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame = buf.tobytes()
            time.sleep(0.1)
        else:
            time.sleep(0.033)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


# ════════════════════════════════════════════════════════════════
# BACKGROUND WORKERS
# ════════════════════════════════════════════════════════════════
def _device_watchdog():
    """Đánh dấu device OFFLINE nếu không nhận heartbeat 30s."""
    while True:
        time.sleep(10)
        now = int(time.time())
        for did, d in devices_state.items():
            if d["status"] == "ONLINE" and (now - d["last_seen"]) > 30:
                with state_lock:
                    d["status"] = "OFFLINE"
                socketio.emit("device_update", {"device_id": did, **d})
                _log_event("WARN", "WATCHDOG", f"Device {d['name']} offline")
                if TB_ACCESS_TOKEN:
                    _push_thingsboard({
                        "device_id": did,
                        "device_name": d.get("name", did),
                        "status": "OFFLINE",
                        "active": False,
                        "lastDisconnectTime": now * 1000,
                    })


def _context_snapshot_worker():
    """Save context snapshot every 60s."""
    while True:
        time.sleep(60)
        with state_lock:
            ctx = dict(context_state)
        try:
            conn = _db_direct()
            conn.execute("""
                INSERT INTO context_snapshots
                (speed_kmh,vehicles_frame,weather,capture_interval,fps,context_ok,ts)
                VALUES(?,?,?,?,?,?,?)
            """, (
                ctx["speed_kmh"], ctx["vehicles_frame"], ctx["weather"],
                ctx["capture_interval"], ctx["fps"],
                1 if ctx["context_ok"] else 0, int(time.time())
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass


def _daily_stats_reset():
    """
    Reset violations_today at midnight + handle data expiry (spec mục 6B).

    Retention policy:
    - Record > 30 ngày → status = EXPIRED (ẩn khỏi dashboard, vẫn trong DB)
    - Ảnh của record EXPIRED → giữ nguyên (admin xem lại được)
    - Record EXPIRED > 90 ngày → soft delete hoàn toàn (tiết kiệm bộ nhớ)
    """
    while True:
        now = datetime.now()
        from datetime import timedelta as _td
        # timedelta avoids month-end day overflow (e.g. Jan 31 + 1 day → Feb 1).
        next_midnight = (now + _td(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        sleep_secs = (next_midnight - now).total_seconds()
        time.sleep(max(sleep_secs, 60))

        with state_lock:
            system_stats["violations_today"] = 0
            context_state["violations_today"] = 0
        log.info("📊 Reset violations_today at midnight")

        # ── Data Expiry ──────────────────────────────────────────
        try:
            conn = _db_direct()
            # 1. Mark EXPIRED: records older than 30 days not yet deleted
            res = conn.execute("""
                UPDATE violations
                SET status = 'EXPIRED'
                WHERE status NOT IN ('DELETED', 'EXPIRED')
                  AND violation_ts < ?
            """, (int(time.time()) - 30 * 86400,))
            expired_count = res.rowcount

            # 2. Soft delete: EXPIRED records older than 90 days
            res2 = conn.execute("""
                UPDATE violations
                SET status = 'DELETED'
                WHERE status = 'EXPIRED'
                  AND violation_ts < ?
            """, (int(time.time()) - 90 * 86400,))
            deleted_count = res2.rowcount

            conn.commit()
            conn.close()

            if expired_count or deleted_count:
                log.info("🗄️  Data retention: %d EXPIRED, %d deleted (>90 days)",
                         expired_count, deleted_count)
                _log_event("INFO", "SYSTEM",
                    f"Data retention: {expired_count} expired (>30 days), "
                    f"{deleted_count} deleted (>90 days)")
        except Exception as e:
            log.error("_daily_stats_reset expiry: %s", e)



# ════════════════════════════════════════════════════════════════
# REST API — Authentication
# ════════════════════════════════════════════════════════════════
# In-memory brute-force protection: max 10 failed logins per IP per 5 min.
_login_failures: dict = {}
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_S     = 300


def _check_login_rate(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_failures.get(ip, []) if now - t < _LOGIN_WINDOW_S]
    _login_failures[ip] = attempts
    return len(attempts) < _LOGIN_MAX_ATTEMPTS


def _record_login_failure(ip: str) -> None:
    _login_failures.setdefault(ip, []).append(time.time())


@app.route("/api/login", methods=["POST"])
def api_login():
    client_ip = request.remote_addr or "unknown"
    if not _check_login_rate(client_ip):
        _log_event("WARN", "AUTH", f"Rate-limited login from {client_ip}")
        return jsonify({"ok": False, "error": "Too many login attempts — try again later"}), 429

    d = request.get_json(force=True, silent=True) or {}
    u = (d.get("username") or "").strip()
    p = d.get("password") or ""
    if u == _ADMIN_USER and p == _ADMIN_PASS:
        ts_ms = int(time.time() * 1000)
        token = f"legacy.{base64.b64encode(f'{_ADMIN_USER}:{_ADMIN_ROLE}:{ts_ms}'.encode()).decode()}"
        _log_event("INFO", "AUTH", f"Login OK: {u}")
        return jsonify({"ok": True, "token": token, "role": _ADMIN_ROLE})
    _record_login_failure(client_ip)
    _log_event("WARN", "AUTH", f"Login failed: {u} from {client_ip}")
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401


@app.get("/api/token/verify")
def api_token_verify():
    tok = request.args.get("token", "").strip()
    if not tok:
        auth = request.headers.get("Authorization", "")
        tok  = auth.removeprefix("Bearer ").strip()
    return jsonify({"ok": True, "valid": _is_valid_token(tok),
                    "token_preview": tok[:10] + "..." if tok else ""})


# ════════════════════════════════════════════════════════════════
# REST API — Bootstrap & Core Data
# ════════════════════════════════════════════════════════════════
@app.get("/api/bootstrap")
def api_bootstrap():
    """Full bootstrap data for Dashboard."""
    db  = get_db(); cur = db.cursor()
    cur.execute("""
        SELECT id,plate_text,plate_confidence,vehicle_type,light_state,speed_kmh,
               full_image_path,plate_image_path,camera_id,violation_ts,status,
               location_name,location_address,location_district,location_city,
               location_direction,station_id,vehicles_frame,roi_name
        FROM violations WHERE status != 'DELETED'
        ORDER BY violation_ts DESC LIMIT 20
    """)
    violations = [_row_to_violation(r) for r in cur.fetchall()]

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM violations WHERE date(violation_time)=? AND status!='DELETED'",
                (today,))
    today_cnt = cur.fetchone()[0]

    cur.execute("SELECT level,source,message,ts FROM system_events ORDER BY ts DESC LIMIT 30")
    events = [dict(r) for r in cur.fetchall()]

    with state_lock:
        t    = dict(traffic_state)
        ctx  = dict(context_state)
        devs = {k: dict(v) for k, v in devices_state.items()}
        st   = dict(system_stats)

    st["uptime_s"]         = int(time.time() - st["start_time"])
    st["violations_today"] = today_cnt

    return jsonify({
        "ok":                   True,
        "traffic":              t,
        "context":              ctx,
        "context_limits":       CONTEXT_LIMITS,
        "camera_optimal":       CAMERA_OPTIMAL,
        "devices":              devs,
        "violations":           violations,
        "events":               events,
        "stats":                st,
        "laptop_camera_active": _laptop_cam_active,
        "laptop_flip_mode":     "css_client_side",
        "server_version":       "7.0",
        "location":             get_location_info(),
    })


@app.get("/api/violations")
@require_token
def api_get_violations():
    """Violation list with filters and pagination."""
    db  = get_db(); cur = db.cursor()
    pg  = max(1, int(request.args.get("page", 1)))
    pp  = min(100, int(request.args.get("per_page", 20)))
    pq  = request.args.get("plate", "").strip().upper()
    lq  = request.args.get("light", "").upper()
    dq  = request.args.get("date", "")
    tq  = request.args.get("type", "").upper()
    sq  = request.args.get("status", "")
    off = (pg - 1) * pp

    w, p = ["status != 'DELETED'"], []
    if pq:  w.append("plate_text LIKE ?");    p.append(f"%{pq}%")
    if lq:  w.append("light_state=?");        p.append(lq)
    if dq:  w.append("date(violation_time)=?"); p.append(dq)
    if tq:  w.append("vehicle_type=?");        p.append(tq)
    if sq:  w.append("status=?");              p.append(sq)

    wc = " AND ".join(w)
    cur.execute(f"SELECT COUNT(*) FROM violations WHERE {wc}", p)
    total = cur.fetchone()[0]

    cur.execute(f"""
        SELECT id,plate_text,plate_confidence,vehicle_type,light_state,speed_kmh,
               full_image_path,plate_image_path,camera_id,violation_ts,status,
               location_name,location_address,location_district,location_city,
               location_direction,station_id,vehicles_frame,roi_name,notes
        FROM violations WHERE {wc}
        ORDER BY violation_ts DESC LIMIT ? OFFSET ?
    """, p + [pp, off])

    return jsonify({
        "ok":      True,
        "data":    [_row_to_violation(r) for r in cur.fetchall()],
        "total":   total,
        "page":    pg, "per_page": pp,
        "pages":   max(1, -(-total // pp)),
    })


@app.get("/api/violations/latest")
@require_token
def api_violations_latest():
    """
    10 most recent violations — for realtime polling (setInterval).
    Frontend can call every 3-5 seconds as Socket.IO alternative.
    """
    db  = get_db(); cur = db.cursor()
    lim = min(50, int(request.args.get("limit", 10)))
    cur.execute("""
        SELECT id,plate_text,plate_confidence,vehicle_type,light_state,speed_kmh,
               full_image_path,plate_image_path,camera_id,violation_ts,status,
               location_name,location_address,location_district,location_city,
               location_direction,station_id,vehicles_frame,roi_name,notes
        FROM violations WHERE status != 'DELETED' AND status != 'EXPIRED'
        ORDER BY violation_ts DESC LIMIT ?
    """, (lim,))
    return jsonify({
        "ok":   True,
        "data": [_row_to_violation(r) for r in cur.fetchall()],
        "ts":   int(time.time()),
    })



@app.delete("/api/violations/<int:vid>")
@require_token
def api_delete_violation(vid: int):
    db = get_db()
    db.execute("UPDATE violations SET status='DELETED' WHERE id=?", (vid,))
    db.commit()
    _log_event("INFO", "API", f"Violation #{vid} đã xóa (soft delete)")
    return jsonify({"ok": True})


@app.put("/api/violations/<int:vid>")
@require_token
def api_update_violation(vid: int):
    """
    Cập nhật violations — Level 3: Quản trị viên sửa tay.
    Hỗ trợ: notes, status, plate_text (sửa license plate OCR sai).
    """
    d = request.get_json(force=True, silent=True) or {}
    db = get_db()

    # Level 3: Admin sửa license plate khi OCR sai / UNKNOWN
    sets, vals = [], []
    if "plate_text" in d:
        sets.append("plate_text=?"); vals.append(d["plate_text"].strip().upper())
    if "notes" in d:
        sets.append("notes=?"); vals.append(d["notes"])
    if "status" in d:
        valid_statuses = ("NEW", "REVIEWED", "EXPIRED", "DELETED")
        if d["status"].upper() in valid_statuses:
            sets.append("status=?"); vals.append(d["status"].upper())
    if not sets:
        return jsonify({"ok": False, "error": "No fields to update"}), 400

    vals.append(vid)
    db.execute(f"UPDATE violations SET {', '.join(sets)} WHERE id=?", vals)
    db.commit()
    _log_event("INFO", "API", f"Violation #{vid} updated: {list(d.keys())}")
    return jsonify({"ok": True})


@app.post("/api/violations/<int:vid>/replace-plate-image")
@require_token
def api_replace_plate_image(vid: int):
    """
    Thay ảnh crop license plate cho record đã có (spec mục 8).
    Admin upload ảnh mới khi ảnh cũ sai hoặc không rõ.

    Form: multipart/form-data với field "plate_image"
    """
    if "plate_image" not in request.files:
        return jsonify({"ok": False, "error": "Missing plate_image file"}), 400

    f = request.files["plate_image"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty file"}), 400

    # Kiểm tra record tồn tại
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id, plate_text FROM violations WHERE id=? AND status!='DELETED'", (vid,))
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Không tìm thấy violations"}), 404

    plate = row["plate_text"] or str(vid)
    ts_now = int(time.time())
    safe   = _safe_plate_filename(str(plate))
    ext    = Path(f.filename).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return jsonify({"ok": False, "error": "Only jpg/jpeg/png/webp allowed"}), 400
    fname  = f"{safe}_{ts_now}_plate_ref{ext}"
    save_path = IMAGE_DIR / fname
    f.save(str(save_path))

    plate_url = f"/imge/{fname}"
    db.execute("UPDATE violations SET plate_image_path=? WHERE id=?", (plate_url, vid))
    db.commit()
    _log_event("INFO", "API", f"Violation #{vid}: thay ảnh license plate → {plate_url}")
    return jsonify({"ok": True, "plate_image_url": plate_url})


@app.post("/api/violations/<int:vid>/replace-full-image")
@require_token
def api_replace_full_image(vid: int):
    """Thay ảnh toàn cảnh cho record."""
    if "full_image" not in request.files:
        return jsonify({"ok": False, "error": "Missing full_image file"}), 400

    f = request.files["full_image"]
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id, plate_text FROM violations WHERE id=? AND status!='DELETED'", (vid,))
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Không tìm thấy violations"}), 404

    ts_now = int(time.time())
    ext    = Path(f.filename).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return jsonify({"ok": False, "error": "Only jpg/jpeg/png/webp allowed"}), 400
    fname  = f"VIOLATION_{vid}_{ts_now}_full{ext}"
    save_path = IMAGE_DIR / fname
    f.save(str(save_path))

    full_url = f"/imge/{fname}"
    db.execute("UPDATE violations SET full_image_path=? WHERE id=?", (full_url, vid))
    db.commit()
    _log_event("INFO", "API", f"Violation #{vid}: thay ảnh gốc → {full_url}")
    return jsonify({"ok": True, "image_url": full_url})


@app.post("/api/upload-violation")
@require_token
def api_upload_violation():
    """
    Upload ảnh violations từ camera IP thật hoặc ESP32-CAM (spec mục 3).
    Server nhận ảnh → detect → OCR → lưu → emit SocketIO.

    Hỗ trợ:
    - multipart/form-data: field "image" (ảnh), "plate" (license plate), "camera_id", "light_state"
    - JSON: {"image_b64": "...", "plate_text": "...", ...}
    """
    ts_now = int(time.time())
    j = request.get_json(force=False, silent=True) or {}

    cam    = (request.form.get("camera_id") or request.args.get("camera_id") or j.get("camera_id") or j.get("cam_id") or "CAM_UPLOAD")
    plate  = (request.form.get("plate") or request.form.get("plate_text") or j.get("plate") or j.get("plate_text") or "").strip().upper()
    vtype  = (request.form.get("vehicle_type") or request.form.get("type") or j.get("vehicle_type") or j.get("type") or "CAR").upper()
    speed  = float(request.form.get("speed_kmh", j.get("speed_kmh", 0)) or 0)
    conf   = float(request.form.get("confidence", j.get("plate_confidence", j.get("confidence", 0))) or 0)
    light  = (request.form.get("light_state") or request.form.get("light") or j.get("light_state") or j.get("light") or "RED").upper()

    image_url  = ""
    plate_url  = ""

    # ── Lưu ảnh gốc violations ──
    if "image" in request.files:
        f = request.files["image"]
        if f and f.filename:
            safe  = _safe_plate_filename(plate or f"upload_{ts_now}")
            fname = f"{safe}_{ts_now}.jpg"
            fpath = IMAGE_DIR / fname
            try:
                img_bytes = f.read()
                fpath.write_bytes(img_bytes)
                image_url = f"/imge/{fname}"
            except Exception as e:
                log.error("upload-violation save image: %s", e)
    else:
        # JSON: image_b64 or existing image_url/full_image_path
        image_b64 = (j.get("image_b64") or j.get("full_image_b64") or "").strip()
        image_url = (j.get("image_url") or j.get("full_image_path") or j.get("full_image_url") or "").strip()
        if image_b64 and not image_url:
            try:
                raw = base64.b64decode(image_b64)
                safe = _safe_plate_filename(plate or f"upload_{ts_now}")
                fname = f"{safe}_{ts_now}.jpg"
                fpath = IMAGE_DIR / fname
                fpath.write_bytes(raw)
                image_url = f"/imge/{fname}"
            except Exception as e:
                log.error("upload-violation json image_b64: %s", e)
        # accept pre-saved local URLs
        if image_url and (image_url.startswith("/imge/") or image_url.startswith("/static/uploads/")) and not _image_url_exists(image_url):
            image_url = ""

    # ── Không lưu ảnh plate riêng ──
    plate_url = image_url

    # Inject vào process_violation
    payload = {
        "plate_text":      plate or "UNKNOWN",
        "vehicle_type":    vtype,
        "speed_kmh":       speed,
        "plate_confidence": conf,
        "camera_id":       cam,
        "ts":              ts_now,
        "image_url":       image_url,
        "plate_image_path":plate_url,
        "light_state":     light,
    }

    # _force_process=True: no need to mutate global traffic_state just to pass the RED check.
    threading.Thread(target=process_violation, args=(payload,),
                     kwargs={"_force_process": True}, daemon=True).start()

    return jsonify({
        "ok":           True,
        "message":      "Violation đã tiếp nhận",
        "image_url":    image_url,
        "plate_url":    plate_url,
        "plate":        plate or "UNKNOWN",
        "ts":           ts_now,
    })



@app.get("/api/violations/<int:vid>")
@require_token
def api_get_violation(vid: int):
    db  = get_db(); cur = db.cursor()
    cur.execute("SELECT * FROM violations WHERE id=?", (vid,))
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "data": _row_to_violation(row)})


# ════════════════════════════════════════════════════════════════
# REST API — CSV Import/Export (csv_importer.py)
# ════════════════════════════════════════════════════════════════
@app.post("/api/violations/import")
@require_token
def api_import_csv():
    """Import violations from uploaded CSV file."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    f = request.files["file"]
    if not (f.filename or "").lower().endswith(".csv"):
        return jsonify({"ok": False, "error": "Only CSV files are supported"}), 400

    tmp_path = BASE_DIR / f"tmp_import_{int(time.time())}.csv"
    f.save(str(tmp_path))

    try:
        from csv_importer import CSVImporter
        importer = CSVImporter(DB_PATH)
        ok = importer.import_from_csv(str(tmp_path))
        tmp_path.unlink(missing_ok=True)
        if ok:
            _log_event("INFO", "CSV", f"Import {importer.imported_count} violations từ CSV")
            return jsonify({
                "ok": True,
                "imported": importer.imported_count,
                "errors":   importer.error_count,
            })
        return jsonify({"ok": False, "error": "Import thất bại"}), 500
    except ImportError:
        # Fallback tự xử lý CSV nếu csv_importer không load được
        import csv
        count = 0
        conn = _db_direct()
        with open(str(tmp_path), "r", encoding="utf-8") as csvf:
            reader = csv.DictReader(csvf)
            for row in reader:
                try:
                    ts = int(datetime.now().timestamp())
                    plate = (row.get("plate_text") or row.get("plate") or "UNKNOWN").strip().upper()
                    vtype = (row.get("vehicle_type") or row.get("type") or "CAR")
                    light = (row.get("light_state") or "RED").upper()
                    image_url = row.get("full_image_path") or row.get("image_url") or ""
                    plate_url = row.get("plate_image_path") or ""
                    date_str = (row.get("date_str") or datetime.fromtimestamp(ts).strftime("%Y-%m-%d"))

                    _insert_violation(conn, {
                        "plate_text":       plate,
                        "plate_confidence": float(row.get("plate_confidence") or row.get("confidence") or 0),
                        "vehicle_type":     str(vtype).upper(),
                        "light_state":      light,
                        "speed_kmh":        float(row.get("speed_kmh", 0) or 0),
                        "full_image_path":  image_url,
                        "plate_image_path": plate_url,
                        "camera_id":        row.get("camera_id") or row.get("cam_id") or "CAM_01",
                        "violation_ts":     ts,
                        "violation_time":   datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                        "status":           "NEW",

                        "plate":            plate,
                        "type":             str(vtype).upper(),
                        "image_url":        image_url,
                        "cam_id":           row.get("camera_id") or row.get("cam_id") or "CAM_01",
                        "ts":               ts,
                        "date_str":         date_str,
                        "processed":        1,
                    })
                    count += 1
                except Exception:
                    pass
        conn.commit()
        conn.close()
        tmp_path.unlink(missing_ok=True)
        return jsonify({"ok": True, "imported": count, "errors": 0})


@app.get("/api/violations/export")
@require_token
def api_export_csv():
    """Export violations to CSV."""
    import csv
    import io

    limit = request.args.get("limit")
    db  = get_db(); cur = db.cursor()
    query = """
        SELECT id,plate_text,plate_confidence,vehicle_type,light_state,speed_kmh,
               violation_ts,full_image_path,plate_image_path,camera_id,esp32_id,
               status,location_name,location_district,location_city
        FROM violations WHERE status!='DELETED'
        ORDER BY violation_ts DESC
    """
    if limit:
        cur.execute(query + " LIMIT ?", (int(limit),))
    else:
        cur.execute(query)

    rows = cur.fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID","Biển Số","Độ Chính Xác OCR","Loại Xe","Trạng Thái Đèn",
                     "Tốc Độ (km/h)","Thời Gian Vi Phạm","Ảnh Gốc","Ảnh Biển Số",
                     "Camera","ESP32","Trạng Thái","Địa Điểm","Quận","Thành Phố"])
    for r in rows:
        r = dict(r)
        ts = r.get("violation_ts") or 0
        vt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
        writer.writerow([
            r["id"], r["plate_text"], r["plate_confidence"],
            r["vehicle_type"], r["light_state"], r["speed_kmh"], vt,
            r["full_image_path"], r["plate_image_path"],
            r["camera_id"], r.get("esp32_id", ""),
            r["status"], r.get("location_name",""),
            r.get("location_district",""), r.get("location_city",""),
        ])

    out.seek(0)
    from flask import make_response
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"]        = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=violations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return resp


# ════════════════════════════════════════════════════════════════
# REST API — Traffic Control
# ════════════════════════════════════════════════════════════════
@app.post("/api/traffic/force")
@require_token
def api_force_light():
    d = request.get_json(force=True) or {}
    l = d.get("light", "RED").upper()
    if l not in ("RED", "YELLOW", "GREEN"):
        return jsonify({"ok": False, "error": "Invalid light state"}), 400
    force_light(l, "EMERGENCY")
    _log_event("WARN", "API", f"Forced light: {l}")
    return jsonify({"ok": True, "light": l})


@app.post("/api/traffic/auto")
@require_token
def api_reset_auto():
    reset_auto()
    _log_event("INFO", "API", "Restored AUTO mode")
    return jsonify({"ok": True, "mode": "AUTO"})


@app.put("/api/traffic/cycle")
@require_token
def api_update_cycle():
    d = request.get_json(force=True) or {}
    with state_lock:
        c = traffic_state["cycle"]
        if "green_duration"  in d: c["green_duration"]  = max(5, int(d["green_duration"]))
        if "yellow_duration" in d: c["yellow_duration"] = max(3, int(d["yellow_duration"]))
        if "red_duration"    in d: c["red_duration"]    = max(5, int(d["red_duration"]))
    return jsonify({"ok": True, "cycle": traffic_state["cycle"]})


@app.get("/api/traffic/state")
@require_token
def api_traffic_state():
    with state_lock:
        return jsonify({"ok": True, "traffic": dict(traffic_state)})


# ════════════════════════════════════════════════════════════════
# REST API — Devices
# ════════════════════════════════════════════════════════════════
@app.get("/api/devices")
@require_token
def api_devices():
    with state_lock:
        devs = {k: dict(v) for k, v in devices_state.items()}
    # Augment with info from device_status DB
    try:
        db  = get_db(); cur = db.cursor()
        cur.execute("SELECT * FROM device_status")
        for row in cur.fetchall():
            r = dict(row)
            did = r.get("device_id", "")
            if did in devs:
                devs[did]["ip"]      = r.get("ip_address", devs[did].get("ip", ""))
                devs[did]["fw"]      = r.get("firmware_version", devs[did].get("fw", ""))
                devs[did]["signal"]  = r.get("signal_strength", devs[did].get("signal", 0))
                devs[did]["temp"]    = r.get("cpu_temp_c", devs[did].get("temp", 0))
                devs[did]["uptime"]  = r.get("uptime_seconds", devs[did].get("uptime", 0))
    except Exception:
        pass
    return jsonify({"ok": True, "devices": devs})


# ════════════════════════════════════════════════════════════════
# REST API — Context & Stats
# ════════════════════════════════════════════════════════════════
@app.get("/api/device-status")
@require_token
def api_device_status():
    """
    Alias của /api/devices — khớp với spec mục 5 & 13.
    Trả về trạng thái camera + ESP32 với heartbeat check.
    Device bị đánh dấu OFFLINE nếu > 15s không có heartbeat.
    """
    OFFLINE_THRESHOLD = 15  # giây

    now = int(time.time())
    with state_lock:
        devs = {k: dict(v) for k, v in devices_state.items()}

    # Đánh dấu OFFLINE nếu quá thời hạn heartbeat
    for did, dv in devs.items():
        last = dv.get("last_seen", 0)
        if last and (now - last) > OFFLINE_THRESHOLD:
            dv["status"] = "OFFLINE"
        dv["last_seen_ago"] = (now - last) if last else None
        dv["heartbeat_ok"]  = bool(last and (now - last) <= OFFLINE_THRESHOLD)

    # Augment with info from device_status DB
    try:
        db = get_db(); cur = db.cursor()
        cur.execute("""
            SELECT device_id, device_name, device_type, is_online, ip_address,
                   heartbeat_ts, signal_strength, cpu_temp_c, uptime_seconds,
                   firmware_version, frames_sent, detections_total, violations_detected
            FROM device_status
        """)
        for row in cur.fetchall():
            r = dict(row)
            did = r.get("device_id", "")
            hts = r.get("heartbeat_ts", 0) or 0
            online = bool(r.get("is_online")) and (now - hts) <= OFFLINE_THRESHOLD

            entry = devs.get(did, {})
            entry.update({
                "device_id":   did,
                "name":        r.get("device_name", did),
                "device_type": r.get("device_type", ""),
                "ip":          r.get("ip_address", entry.get("ip", "")),
                "fw":          r.get("firmware_version", entry.get("fw", "")),
                "signal":      r.get("signal_strength", entry.get("signal", 0)),
                "temp":        r.get("cpu_temp_c", entry.get("temp", 0)),
                "uptime":      r.get("uptime_seconds", entry.get("uptime", 0)),
                "frames_sent": r.get("frames_sent", 0),
                "detections":  r.get("detections_total", 0),
                "violations":  r.get("violations_detected", 0),
                "status":      "ONLINE" if online else "OFFLINE",
                "last_heartbeat_ts": hts,
                "last_seen_str":     datetime.fromtimestamp(hts).strftime("%H:%M:%S") if hts else "--",
                "heartbeat_ok":      online,
            })
            if did not in devs:
                devs[did] = entry

    except Exception as e:
        log.debug("device-status DB: %s", e)

    return jsonify({"ok": True, "devices": devs, "count": len(devs), "ts": now})


# ════════════════════════════════════════════════════════════════
# REST API — Context & Stats
# ════════════════════════════════════════════════════════════════
@app.get("/api/context")
@require_token
def api_context():
    """
    Current AI context state + 7 context limit validation.
    Returns context_state, CONTEXT_LIMITS, CAMERA_OPTIMAL, and validation result.
    Used by Dashboard to display GH1-GH7 status badges in real-time.
    """
    with state_lock:
        ctx = dict(context_state)
    ok, errs = validate_context(ctx)
    return jsonify({
        "ok":            True,
        "context":       ctx,
        "limits":        CONTEXT_LIMITS,
        "camera_optimal":CAMERA_OPTIMAL,
        "valid":         ok,
        "errors":        errs,
    })


@app.get("/api/events")
@require_token
def api_events():
    lv  = request.args.get("level", "")
    lim = min(200, int(request.args.get("limit", 50)))
    db  = get_db(); cur = db.cursor()
    if lv:
        cur.execute("SELECT * FROM system_events WHERE level=? ORDER BY ts DESC LIMIT ?",
                    (lv.upper(), lim))
    else:
        cur.execute("SELECT * FROM system_events ORDER BY ts DESC LIMIT ?", (lim,))
    return jsonify({"ok": True, "events": [dict(r) for r in cur.fetchall()]})


@app.get("/api/stats")
@require_token
def api_stats():
    db  = get_db(); cur = db.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("SELECT COUNT(*) FROM violations WHERE status!='DELETED'")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM violations WHERE date(violation_time)=? AND status!='DELETED'",
                (today,))
    td = cur.fetchone()[0]

    cur.execute("""
        SELECT strftime('%H', datetime(violation_ts,'unixepoch','localtime')) hr, COUNT(*) cnt
        FROM violations WHERE date(violation_time)=? AND status!='DELETED'
        GROUP BY hr ORDER BY hr
    """, (today,))
    by_h = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("""
        SELECT date(violation_time) d, COUNT(*) cnt
        FROM violations WHERE violation_ts > ? AND status!='DELETED'
        GROUP BY d ORDER BY d
    """, (int(time.time()) - 7 * 86400,))
    by_d = [{"date": r[0], "count": r[1]} for r in cur.fetchall()]

    cur.execute("SELECT vehicle_type,COUNT(*) cnt FROM violations WHERE status!='DELETED' GROUP BY vehicle_type")
    by_t = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT AVG(plate_confidence) FROM violations WHERE violation_ts>? AND status!='DELETED'",
                (int(time.time()) - 86400,))
    ac = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM violations WHERE status='NEW' AND status!='DELETED'")
    pending = cur.fetchone()[0]

    with state_lock:
        st = dict(system_stats)
    st["uptime_s"] = int(time.time() - st["start_time"])

    return jsonify({
        "ok":         True,
        "total":      total,
        "today":      td,
        "pending":    pending,
        "by_hour":    by_h,
        "by_day":     by_d,
        "by_type":    by_t,
        "avg_conf":   round(ac, 3),
        "system":     st,
    })


@app.get("/api/health")
def api_health():
    mqtt_ok = _mqtt_client is not None and _mqtt_client.is_connected()
    return jsonify({
        "ok":             True,
        "server":         "AI Traffic Control v7.0",
        "time":           int(time.time()),
        "mqtt":           mqtt_ok,
        "uptime":         int(time.time() - system_stats["start_time"]),
        "laptop_cam":     _laptop_cam_active,
        "flip_mode":      "css_client_side",
        "version":        "7.0",
        "context_limits": CONTEXT_LIMITS,
    })


# ════════════════════════════════════════════════════════════════
# REST API — Inject & Seed (Testing)
# ════════════════════════════════════════════════════════════════
@app.post("/api/violations/inject")
@require_token
def api_inject():
    """Inject test violation."""
    d = request.get_json(force=True) or {}
    d.setdefault("ts", int(time.time()))
    d.setdefault("plate", "51B-12345")
    d.setdefault("type", "MOTORBIKE")
    d.setdefault("speed_kmh", 14.2)
    d.setdefault("confidence", 0.88)
    d.setdefault("cam_id", "CAM_01")
    # No global state mutation needed — _force_process bypasses the RED-light gate.
    threading.Thread(target=process_violation, args=(d,),
                     kwargs={"_force_process": True}, daemon=True).start()
    return jsonify({"ok": True, "message": "Violation test đã inject"})


@app.post("/api/seed")
@require_token
def api_seed():
    """Manual database seed."""
    threading.Thread(target=_seed_if_empty, daemon=True).start()
    return jsonify({"ok": True, "message": "Seeding in progress"})


# ════════════════════════════════════════════════════════════════
# REST API — Location
# ════════════════════════════════════════════════════════════════
@app.get("/api/location/current")
@require_token
def api_location_current():
    now = datetime.now()
    weekdays = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"]
    loc = get_location_info()
    return jsonify({
        "ok":           True,
        "lat":          CAM_LAT,
        "lng":          CAM_LNG,
        "address":      loc["full_address"],
        "street":       loc["street"],
        "intersection": loc["intersection"],
        "district":     loc["district"],
        "city":         loc["city"],
        "direction":    loc["direction"],
        "station_id":   loc["station_id"],
        "cam_name":     loc["cam_name"],
        "maps_url":     f"https://www.google.com/maps?q={CAM_LAT},{CAM_LNG}",
        "time_str":     now.strftime("%H:%M:%S"),
        "date_str":     now.strftime("%d/%m/%Y"),
        "date_vn":      f"{weekdays[now.weekday()]}, {now.strftime('%d/%m/%Y')}",
        "timestamp":    int(time.time()),
    })


@app.post("/api/update_location")
@require_token
def api_update_location():
    global CAM_LAT, CAM_LNG, CAM_STREET, CAM_DISTRICT, CAM_CITY, CAM_INTERSECTION
    d = request.get_json(force=True, silent=True) or {}
    if d.get("lat"):      CAM_LAT          = str(d["lat"])
    if d.get("lng"):      CAM_LNG          = str(d["lng"])
    if d.get("road"):     CAM_STREET       = d["road"]
    if d.get("suburb"):   CAM_INTERSECTION = d["suburb"]
    if d.get("district"): CAM_DISTRICT     = d["district"]
    if d.get("city"):     CAM_CITY         = d["city"]
    log.info("📍 Location updated: %s, %s, %s", CAM_STREET, CAM_DISTRICT, CAM_CITY)
    return jsonify({
        "ok":  True,
        "lat": CAM_LAT, "lng": CAM_LNG,
        "address": f"{CAM_STREET}, {CAM_INTERSECTION}, {CAM_DISTRICT}, {CAM_CITY}"
    })


# ════════════════════════════════════════════════════════════════
# REST API — Theme (main.js cần /api/theme)
# ════════════════════════════════════════════════════════════════
_theme_config = {
    "mode": "dark", "accent": "#20caff", "primary": "#020917",
    "success": "#00e87a", "warning": "#ffb020", "danger": "#ff3a5c",
}


@app.get("/api/theme")
def api_theme_get():
    return jsonify({"ok": True, "theme": _theme_config})


@app.post("/api/theme")
@require_token
def api_theme_set():
    d = request.get_json(force=True, silent=True) or {}
    _theme_config.update({k: v for k, v in d.items() if k in _theme_config})
    return jsonify({"ok": True, "theme": _theme_config})


# ════════════════════════════════════════════════════════════════
# REST API — Laptop Camera
# ════════════════════════════════════════════════════════════════
@app.post("/api/laptop_camera/start")
@require_token
def api_laptop_start():
    global _laptop_cam_thread, _laptop_frame, _laptop_frame_raw, _laptop_cam_stop_evt

    with _laptop_cam_lock:
        if _laptop_cam_thread is not None and _laptop_cam_thread.is_alive():
            if _laptop_cam_stop_evt is not None:
                _laptop_cam_stop_evt.set()
            _laptop_cam_thread.join(timeout=2.0)

        new_stop_event      = threading.Event()
        _laptop_cam_stop_evt = new_stop_event
        with _laptop_frame_lock:
            _laptop_frame     = None
            _laptop_frame_raw = None

        _laptop_cam_thread = threading.Thread(
            target=_laptop_cam_worker, args=(new_stop_event,),
            name="LaptopCam", daemon=True
        )
        _laptop_cam_thread.start()

    _log_event("INFO", "LAPTOP_CAM", "Laptop camera started v7.0")
    return jsonify({"ok": True, "status": "started", "flip_mode": "css_client_side"})


@app.post("/api/laptop_camera/stop")
@require_token
def api_laptop_stop():
    global _laptop_frame, _laptop_frame_raw
    with _laptop_cam_lock:
        if _laptop_cam_stop_evt is not None:
            _laptop_cam_stop_evt.set()
        with _laptop_frame_lock:
            _laptop_frame     = None
            _laptop_frame_raw = None
    _log_event("INFO", "LAPTOP_CAM", "Laptop camera stopped")
    return jsonify({"ok": True, "status": "stopping"})


@app.get("/api/laptop_camera/status")
@require_token
def api_laptop_status():
    with state_lock:
        ctx = dict(context_state)
    ctx_ok, ctx_err = validate_context(ctx)
    return jsonify({
        "ok":              True,
        "active":          _laptop_cam_active,
        "frame_ready":     _laptop_frame is not None,
        "context_ok":      ctx_ok,
        "context_errors":  ctx_err,
        "traffic_light":   traffic_state["light"],
        "camera_mode":     traffic_state["camera"],
        "flip_mode":       "css_client_side",
        "frame_orientation": "straight",
    })


@app.get("/api/laptop_camera/ready")
@require_token
def api_laptop_ready():
    with _laptop_frame_lock:
        frame_ready = _laptop_frame is not None
    return jsonify({
        "ok":              True,
        "frame_ready":     frame_ready,
        "active":          _laptop_cam_active,
        "frame_orientation": "straight",
    })


@app.post("/api/laptop_camera/flip")
@require_token
def api_laptop_flip():
    global _laptop_flip_display
    d = request.get_json(force=True, silent=True) or {}
    _laptop_flip_display = bool(d.get("flip", not _laptop_flip_display))
    _log_event("INFO", "LAPTOP_CAM", f"Server-side flip: {'ON' if _laptop_flip_display else 'OFF'}")
    return jsonify({"ok": True, "flip_display": _laptop_flip_display})


@app.post("/api/laptop_camera/snapshot")
@require_token
def api_laptop_snapshot():
    """Take snapshot from laptop camera + record violation if light is RED."""
    data   = request.get_json(force=True, silent=True) or {}
    plate  = (data.get("plate") or "").strip().upper()
    inject = data.get("inject_violation", False)
    image_b64 = (data.get("image_b64") or "").strip()
    image_data_url = (data.get("image_data_url") or "").strip()

    frame_bytes = b""
    # Prefer browser snapshot if provided (real laptop camera in browser)
    if image_data_url.startswith("data:") and "," in image_data_url:
        try:
            image_b64 = image_data_url.split(",", 1)[1].strip()
        except Exception:
            pass
    if image_b64:
        try:
            frame_bytes = base64.b64decode(image_b64)
        except Exception:
            frame_bytes = b""

    if not frame_bytes:
        with _laptop_frame_lock:
            frame_bytes = _laptop_frame_raw if _laptop_frame_raw is not None else _laptop_frame

    # Không có frame thật → từ chối ngay, không dùng placeholder
    if not frame_bytes:
        return jsonify({"ok": False, "error": "Không có frame camera — hãy bật webcam rồi thử lại.", "plate": ""}), 400

    # Default: server will try to OCR (avoid storing SNAP_LAPTOP as "license plate")
    if not plate:
        plate = "AUTO_DETECT"

    # OCR if user did not provide a plate (or left it as default)
    ocr_plate, ocr_conf, ocr_bbox = ("", 0.0, None)
    if plate in {"SNAP_LAPTOP", "AUTO_DETECT", "UNKNOWN"} or not _canon_plate(plate):
        ocr_plate, ocr_conf, ocr_bbox = _ocr_plate_from_jpg_bytes_with_bbox(frame_bytes)
        if ocr_plate:
            plate = ocr_plate
    if plate in {"AUTO_DETECT", "SNAP_LAPTOP"} or not _canon_plate(plate):
        plate = "UNKNOWN"

    # Vehicle type detection: prefer request -> YOLO -> fallback
    vtype = (data.get("vehicle_type") or data.get("type") or "").upper()
    vehicles_frame = int(data.get("vehicles_frame", 0) or 0)
    yolo_conf = 0.0
    if not vtype or vtype not in ("CAR", "MOTORBIKE"):
        try:
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            img0 = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            img0 = None
        yolo_type, yolo_conf, yolo_cnt = _detect_vehicle_type_from_img(img0)
        if yolo_type:
            vtype = yolo_type
            vehicles_frame = max(vehicles_frame, int(yolo_cnt or 0))
        else:
            vtype = "CAR"

    plate_url = ""

    with state_lock:
        cur_light = traffic_state["light"]

    # Chỉ ghi vi phạm khi: có biển số thật (OCR đọc được) + đèn đỏ/inject
    plate_real = plate and plate not in {"UNKNOWN", "AUTO_DETECT", "SNAP_LAPTOP"} and _canon_plate(plate)

    # Chỉ lưu ảnh khi OCR đọc được biển số hợp lệ
    image_url = ""
    if frame_bytes and plate_real:
        try:
            ts_now = int(time.time())
            image_url = _save_direct_violation_frame(frame_bytes, plate, ts_now, "laptop")
        except Exception as e:
            log.error("Lưu ảnh laptop: %s", e)

    plate_url = image_url
    injected_ok = False
    if plate_real and (inject or cur_light == "RED"):
        conf_from_req = float(data.get("confidence", 0.0) or 0.0)
        conf_out = max(conf_from_req, float(ocr_conf or 0.0))
        vd = {
            "ts":            int(time.time()),
            "plate":         plate,
            "type":          vtype,
            "speed_kmh":     float(data.get("speed_kmh", 14.2)),
            "confidence":    conf_out if conf_out > 0 else 0.87,
            "image_url":     image_url,
            "plate_url":     plate_url,
            "cam_id":        "LAPTOP_CAM",
            "roi":           "STOP_LINE",
            "vehicles_frame":max(1, vehicles_frame or 1),
        }
        threading.Thread(target=process_violation, args=(vd,),
                         kwargs={"_force_process": True}, daemon=True).start()
        _log_event("WARN", "LAPTOP_CAM", f"📸 Ghi vi phạm: {plate} ({vtype}) đèn={cur_light}")
        injected_ok = True
    elif not plate_real:
        _log_event("INFO", "LAPTOP_CAM", f"OCR không đọc được biển số — không ghi vi phạm")

    canon = _canon_plate(plate if plate_real else "")
    samples = _load_reference_plate_sources()
    sample_row = samples.get(canon) if canon else None
    db_res = _db_lookup_plate_canon(canon) if canon else {"found": False, "latest": None}

    return jsonify({
        "ok":               True,
        "image_url":        image_url,
        "plate_image_url":  image_url,
        "plate":            plate if plate_real else "",
        "vehicle_type":     vtype,
        "ocr_confidence":   float(ocr_conf or 0.0),
        "yolo_confidence":  float(yolo_conf or 0.0),
        "vehicles_frame":   int(max(vehicles_frame or 0, 0)),
        "light":            cur_light,
        "injected":         injected_ok,
        "found": {
            "sample": bool(sample_row),
            "db": bool(db_res.get("found")),
        },
        "sample": sample_row,
        "db": db_res.get("latest"),
        "frame_orientation":"straight",
    })


def _db_lookup_plate_canon(canon: str) -> dict:
    canon = _canon_plate(canon)
    if not canon:
        return {"found": False, "latest": None}
    try:
        conn = _db_direct()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Canonical compare in SQL (strip -, space, dot).
        q = """
            SELECT * FROM violations
            WHERE status!='DELETED' AND (
                REPLACE(REPLACE(REPLACE(UPPER(COALESCE(plate_text,'')),'-',''),' ',''),'.','') = ?
                OR
                REPLACE(REPLACE(REPLACE(UPPER(COALESCE(plate,'')),'-',''),' ',''),'.','') = ?
            )
            ORDER BY violation_ts DESC
            LIMIT 1
        """
        cur.execute(q, (canon, canon))
        r = cur.fetchone()
        conn.close()
        if not r:
            return {"found": False, "latest": None}
        d = dict(r)
        return {
            "found": True,
            "latest": {
                "id": d.get("id"),
                "plate_text": d.get("plate_text") or d.get("plate") or "",
                "vehicle_type": d.get("vehicle_type") or d.get("type") or "",
                "light_state": d.get("light_state") or d.get("light") or "",
                "speed_kmh": d.get("speed_kmh") or 0,
                "violation_ts": d.get("violation_ts") or d.get("ts") or 0,
                "full_image_path": d.get("full_image_path") or d.get("image_url") or "",
                "plate_image_path": d.get("plate_image_path") or d.get("plate_url") or "",
                "camera_id": d.get("camera_id") or d.get("cam_id") or "",
                "status": d.get("status") or "",
            },
        }
    except Exception:
        return {"found": False, "latest": None}


@app.get("/api/plate/lookup")
@require_token
def api_plate_lookup():
    plate = (request.args.get("plate") or "").strip().upper()
    canon = _canon_plate(plate)
    samples = _load_reference_plate_sources()
    sample_row = samples.get(canon)
    db_res = _db_lookup_plate_canon(canon)
    return jsonify({
        "ok": True,
        "plate": _format_plate(canon) if canon else plate,
        "plate_canon": canon,
        "found": {
            "sample": bool(sample_row),
            "db": bool(db_res.get("found")),
        },
        "sample": sample_row,
        "db": db_res.get("latest"),
    })


@app.post("/api/plate/scan")
@require_token
def api_plate_scan():
    data = request.get_json(force=True, silent=True) or {}
    plate = (data.get("plate") or "").strip().upper()
    image_b64 = (data.get("image_b64") or "").strip()
    image_data_url = (data.get("image_data_url") or "").strip()

    if image_data_url.startswith("data:") and "," in image_data_url:
        try:
            image_b64 = image_data_url.split(",", 1)[1].strip()
        except Exception:
            pass

    ocr_conf = 0.0
    if (not plate or plate in {"SNAP_LAPTOP", "AUTO_DETECT", "UNKNOWN"}) and image_b64:
        try:
            raw = base64.b64decode(image_b64)
        except Exception:
            raw = b""
        if raw:
            ocr_plate, ocr_conf = _ocr_plate_from_jpg_bytes(raw)
            if ocr_plate:
                plate = ocr_plate

    canon = _canon_plate(plate)
    samples = _load_reference_plate_sources()
    sample_row = samples.get(canon)
    db_res = _db_lookup_plate_canon(canon)
    return jsonify({
        "ok": True,
        "plate": _format_plate(canon) if canon else plate,
        "plate_canon": canon,
        "ocr_confidence": float(ocr_conf or 0.0),
        "found": {
            "sample": bool(sample_row),
            "db": bool(db_res.get("found")),
        },
        "sample": sample_row,
        "db": db_res.get("latest"),
    })


# ════════════════════════════════════════════════════════════════
# VIDEO STREAMS
# ════════════════════════════════════════════════════════════════
@app.get("/video_feed")
def video_feed():
    """Stream ESP32-CAM qua MQTT."""
    return Response(_gen_esp32_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/laptop_feed")
def laptop_feed():
    """Stream laptop camera."""
    return Response(_gen_laptop_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ════════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS
# ════════════════════════════════════════════════════════════════
@socketio.on("connect")
def ws_connect():
    with state_lock:
        emit("traffic_state", dict(traffic_state))
        emit("context_update", dict(context_state))
        emit("device_list", {k: dict(v) for k, v in devices_state.items()})
        emit("laptop_cam_status", {
            "active": _laptop_cam_active,
            "flip_mode": "css_client_side",
        })
    log.debug("WebSocket client connected")


@socketio.on("disconnect")
def ws_disconnect():
    log.debug("WebSocket client ngắt connected")


@socketio.on("cmd_force_light")
def ws_force(data):
    l = (data or {}).get("light", "RED").upper()
    if l in ("RED", "YELLOW", "GREEN"):
        force_light(l)
        _log_event("WARN", "WS", f"Force light: {l}")


@socketio.on("cmd_auto")
def ws_auto(_):
    reset_auto()


@socketio.on("ping_server")
def ws_ping(_):
    emit("pong_server", {"ts": int(time.time())})


@socketio.on("cmd_inject_violation")
def ws_inject(data):
    """Inject violations từ WebSocket (test realtime)."""
    d = data or {}
    d.setdefault("ts", int(time.time()))
    d.setdefault("plate", "TEST-99999")
    d.setdefault("type", "CAR")
    d.setdefault("speed_kmh", 16.0)
    d.setdefault("confidence", 0.90)
    d.setdefault("cam_id", "WS_TEST")
    threading.Thread(target=process_violation, args=(d,),
                     kwargs={"_force_process": True}, daemon=True).start()


# ════════════════════════════════════════════════════════════════
# PUBLIC API CHO ai_engine.py
# ════════════════════════════════════════════════════════════════
def get_current_light() -> str:
    with state_lock:
        return traffic_state["light"]


def set_ai_frame(frame_bytes: bytes):
    global latest_frame
    with frame_lock:
        latest_frame = frame_bytes


def update_ai_context(vehicles: int = 0, fps: float = 0.0, **kw):
    with state_lock:
        context_state["vehicles_frame"] = vehicles
        context_state["fps"]            = round(fps, 1)
        if "capture_interval" in kw:
            context_state["capture_interval"] = kw["capture_interval"]
        if "weather" in kw:
            context_state["weather"] = kw["weather"]
        if "distance" in kw:
            context_state["distance"] = kw["distance"]
        ctx = dict(context_state)
    socketio.emit("context_update", ctx)


# ════════════════════════════════════════════════════════════════
# STATIC FILE SERVING — Frontend
# ════════════════════════════════════════════════════════════════
@app.get("/favicon.ico")
def favicon():
    for base in (FRONTEND_DIR, IMAGE_DIR, LEGACY_IMAGE_DIR):
        for name in ("favicon.ico", "favicon.png", "admin.jpg"):
            path = base / name
            if path.exists():
                return send_from_directory(str(base), name)
    return Response(status=204)


@app.get("/")
def root():
    """Home page → main.html (dashboard)."""
    return send_from_directory(str(FRONTEND_DIR), "main.html")


@app.get("/login")
def login_page():
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.get("/index")
def index_page():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.get("/imge/<path:filename>")
def serve_img(filename):
    """
    Serve images from repo-level imge/:
    - /imge/49_E1_999_66_*.jpg     → IMAGE_DIR/49_E1_999_66_*.jpg
    - /imge/frame.jpg              → IMAGE_DIR/frame.jpg
    Cache policy:
    - Captured images under imge/: cacheable to avoid spam refetching
    - Live frames (frame.jpg): no-cache
    """
    def _apply_img_cache_headers(resp, req_path: str):
        try:
            low = (req_path or "").lower()
            # Live / frequently-updated resources should never be cached.
            is_dynamic = low.endswith("frame.jpg") or low.endswith("frame.jpeg") or "/frame." in low
            if is_dynamic or IMAGE_CACHE_MAX_AGE_S <= 0:
                resp.headers.update({
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma":        "no-cache",
                    "Expires":       "0",
                })
                return resp

            cc = f"public, max-age={IMAGE_CACHE_MAX_AGE_S}"
            if IMAGE_CACHE_IMMUTABLE:
                cc += ", immutable"
            resp.headers["Cache-Control"] = cc
            resp.headers.pop("Pragma", None)
            resp.headers.pop("Expires", None)
            return resp
        except Exception:
            return resp

    # Try repo-level IMAGE_DIR first, then legacy server/imge.
    for root_dir in (IMAGE_DIR, LEGACY_IMAGE_DIR):
        try:
            parts = Path(filename).parts
            if len(parts) >= 2:
                subdir = root_dir / parts[0]
                fname  = "/".join(parts[1:])
                target = subdir / fname
                if target.exists():
                    resp = send_from_directory(str(subdir), fname)
                    return _apply_img_cache_headers(resp, filename)

            # Fallback: tìm trực tiếp trong root_dir
            target2 = root_dir / filename
            if target2.exists():
                resp = send_from_directory(str(root_dir), filename)
                return _apply_img_cache_headers(resp, filename)
        except Exception:
            continue

    # Not found anywhere → Flask will respond 404
    resp = send_from_directory(str(IMAGE_DIR), filename)
    return _apply_img_cache_headers(resp, filename)


@app.get("/static/uploads/<path:filename>")
def serve_static_uploads(filename):
    """
    Serve images at /static/uploads/ path — compatible with schema.sql + seed_database.py.
    Paths: /imge/<plate>_<ts>.jpg → IMAGE_DIR/<plate>_<ts>.jpg
    """
    parts = filename.split("/")
    if len(parts) >= 2:
        sub_dir  = IMAGE_DIR / parts[0]
        sub_file = "/".join(parts[1:])
        target   = sub_dir / sub_file
        if target.exists():
            resp = send_from_directory(str(sub_dir), sub_file)
            # Static upload paths map to immutable files (use cache headers like /imge/*).
            try:
                cc = f"public, max-age={IMAGE_CACHE_MAX_AGE_S}"
                if IMAGE_CACHE_IMMUTABLE:
                    cc += ", immutable"
                resp.headers["Cache-Control"] = cc
            except Exception:
                pass
            return resp
    # Fallback
    return send_from_directory(str(IMAGE_DIR), filename)



@app.get("/<path:filename>")
def serve_fe(filename):
    """Fallback: serve static files from frontend directory."""
    # Avoid conflict with API routes
    if filename.startswith("api/"):
        from flask import abort
        abort(404)
    try:
        return send_from_directory(str(FRONTEND_DIR), filename)
    except Exception:
        from flask import abort
        abort(404)


# ════════════════════════════════════════════════════════════════
# VIRTUAL ESP32 CLUSTER — AUTO LAUNCH
# Replace real ESP32 hardware with virtual_esp32_cluster.py
# ════════════════════════════════════════════════════════════════
_cluster_thread: threading.Thread | None = None


def _check_cluster_ready() -> tuple:
    """
    Check prerequisites to run virtual_esp32_cluster.py:
    1. File tồn tại
    2. Mosquitto MQTT Broker đang chạy ở localhost:1883
    3. Thư viện cần thiết có sẵn
    """
    # Locate cluster file
    cluster_file = BASE_DIR / "virtual_esp32_cluster.py"
    if not cluster_file.exists():
        return False, f"virtual_esp32_cluster.py not found tại {BASE_DIR}"

    # Check Mosquitto localhost:1883 (optional — can run direct-mode without broker)
    mqtt_ok = True
    try:
        s = _socket.create_connection(("localhost", 1883), timeout=1.5)
        s.close()
    except OSError:
        mqtt_ok = False

    # Check required libraries
    try:
        import paho.mqtt.client   # noqa
        import cv2                # noqa
        import numpy              # noqa
    except ImportError as e:
        return False, f"Thiếu thư viện: {e}"

    mode = "mqtt" if mqtt_ok else "direct"
    return True, {"path": str(cluster_file), "mode": mode, "mqtt_ok": mqtt_ok}


def _run_cluster_inline(mode: str = "mqtt"):
    """Run virtual_esp32_cluster in dedicated thread via importlib."""
    import traceback
    try:
        cluster_path = BASE_DIR / "virtual_esp32_cluster.py"
        spec = importlib.util.spec_from_file_location("virtual_esp32_cluster", str(cluster_path))
        mod  = importlib.util.module_from_spec(spec)
        _sys.modules["virtual_esp32_cluster"] = mod
        spec.loader.exec_module(mod)

        # DIRECT mode: no external broker needed — wire cluster publish/subscribe to in-process bus.
        if str(mode).lower() == "direct":
            try:
                if hasattr(mod, "enable_direct_mode"):
                    mod.enable_direct_mode(
                        inject_func=mqtt_inject,
                        subscribe_local_func=mqtt_subscribe_local,
                        get_traffic_state_func=lambda: dict(traffic_state),
                    )
                    log.info("[CLUSTER] DIRECT mode wiring OK (no broker).")
                else:
                    log.error("[CLUSTER] Cluster file không hỗ trợ DIRECT mode — hãy updated virtual_esp32_cluster.py")
            except Exception as e:
                log.error("[CLUSTER] DIRECT wiring lỗi: %s", e)

        if hasattr(mod, "CameraNode"):
            node_cls = mod.CameraNode
            if not hasattr(node_cls, "run") and not hasattr(node_cls, "start"):
                log.error("[CLUSTER] File virtual_esp32_cluster.py thiếu method run() — updated file")
                return

        log.info("[CLUSTER] virtual_esp32_cluster.main() bắt đầu...")
        mod.main()

    except KeyboardInterrupt:
        log.info("[CLUSTER] Dừng theo yêu cầu người dùng")
    except AttributeError as e:
        log.error("[CLUSTER] AttributeError: %s — file có thể bị lỗi hoặc quá cũ", e)
        log.error("[CLUSTER] Chi tiết:\n%s", traceback.format_exc())
    except Exception as e:
        log.error("[CLUSTER] Error: %s — %s\n%s", type(e).__name__, e, traceback.format_exc())


def _start_virtual_cluster():
    """
    Check laptop → auto-launch Virtual ESP32 Cluster.
    Cluster will completely replace real ESP32-CAM hardware.
    """
    global _cluster_thread

    print()
    print("=" * 65)
    print("  [APP.PY v7.0] KIỂM TRA VIRTUAL ESP32 CLUSTER...")
    print("=" * 65)

    ok, info = _check_cluster_ready()

    if not ok:
        print(f"  ⚠️  {info}")
        print("  → Virtual ESP32 Cluster KHÔNG chạy.")
        print("  → Hướng dẫn: chạy start_mqtt.bat rồi khởi động lại app.py")
        print("  → Web Dashboard vẫn hoạt động bình thường (không có dữ liệu live)")
        print("=" * 65)
        log.warning("[CLUSTER] Cannot start: %s", info)
        return

    cluster_path = info.get("path")
    cluster_mode = info.get("mode", "mqtt")
    print(f"  ✅ OK — All prerequisites satisfied:")
    print(f"     File  : {cluster_path}")
    if cluster_mode == "mqtt":
        print(f"     MQTT  : localhost:1883 ✓")
    else:
        print(f"     MQTT  : localhost:1883 ✗  → chạy DIRECT mode (không cần broker)")
    print(f"     Libs  : paho-mqtt + opencv + numpy ✓")
    print()
    print("  → Virtual ESP32 Cluster sẽ khởi động sau 3.5s")
    print("  → 3x ESP32-CAM + ESP32 Main + LED 7-Segment (mô phỏng)")
    print("  → Dashboard: http://localhost:5050")
    print("=" * 65)

    log.info("[CLUSTER] Prerequisites met — starting cluster in 3.5s")

    def _delayed():
        time.sleep(3.5)
        log.info("[CLUSTER] =====================================================")
        log.info("[CLUSTER]  VIRTUAL ESP32 CLUSTER v7.0 RUNNING")
        log.info("[CLUSTER]  3x ESP32-CAM | ESP32 Main | LED 7-Segment")
        log.info("[CLUSTER]  MODE → %s", "MQTT localhost:1883" if cluster_mode == "mqtt" else "DIRECT (in-process)")
        log.info("[CLUSTER] =====================================================")
        _run_cluster_inline(cluster_mode)

    _cluster_thread = threading.Thread(target=_delayed, name="VirtualESP32Cluster", daemon=True)
    _cluster_thread.start()


# ════════════════════════════════════════════════════════════════
# BOOTSTRAP — Full system startup
# ════════════════════════════════════════════════════════════════
def _bootstrap():
    global _laptop_cam_stop_evt

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  AI TRAFFIC CONTROL v7.0 — FULL SYSTEM BOOT                ║")
    print("║  ESP32 Virtual Cluster + AI Engine + Dashboard              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  7 Giới hạn ngữ cảnh ESP32:                                 ║")
    print("║  GH1 Vận tốc < 20km/h  GH2 ≤6 xe/frame  GH3 Thời tiết OK ║")
    print("║  GH4 Khoảng cách 5m    GH5 ROI STOP_LINE GH6 500ms chụp   ║")
    print("║  GH7 Chỉ Xe máy & Ô tô                                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    log.info("🚀 AI Traffic Control v7.0 — System startup")

    # 1. Initialize Database
    log.info("💾 Initialize Database...")
    _init_db()
    log.info("Auto-seed disabled on boot — chỉ dùng ảnh chụp thật, không tự tạo ảnh/vi phạm mẫu.")

    # 2. Camera laptop standby
    _laptop_cam_stop_evt = None
    log.info("📷 Laptop camera: standby — ready when user enables")

    # 3. Background workers
    threading.Thread(target=_traffic_cycle_worker,   name="TrafficCycle",   daemon=True).start()
    threading.Thread(target=_device_watchdog,         name="DeviceWatchdog", daemon=True).start()
    threading.Thread(target=_context_snapshot_worker, name="CtxSnapshot",    daemon=True).start()
    threading.Thread(target=_daily_stats_reset,       name="DailyReset",     daemon=True).start()
    log.info("⚙️  Background workers started")

    # 4. MQTT Client
    log.info("📡 Starting MQTT client...")
    _init_mqtt()

    # 5. AI Engine
    try:
        from ai_engine import start_ai
        start_ai(app)
        log.info("🤖 AI Engine OK")
    except ImportError:
        log.info("ℹ️  No ai_engine.py found — running in demo mode")
    except Exception as e:
        log.error("AI Engine: %s", e)

    # 6. Virtual ESP32 Cluster (thay thế phần cứng)
    if VIRTUAL_CLUSTER_AUTOSTART:
        _start_virtual_cluster()
    else:
        log.info("ℹ️  Virtual ESP32 Cluster autostart is OFF")

    # 7. System boot logged
    _log_event("INFO", "SYSTEM", "AI Traffic Control v7.0 — Full system boot")

    print()
    print("✅ SYSTEM READY!")
    print(f"   Dashboard  : http://localhost:5050")
    print(f"   Login      : http://localhost:5050/login")
    print(f"   API Health : http://localhost:5050/api/health")
    print(f"   Auth       : username={_ADMIN_USER}  password=*** (set ADMIN_PASS env var)")
    print(f"   DB         : {DB_PATH}")
    print(f"   Images     : {IMAGE_DIR}")
    print(f"   MQTT       : {MQTT_HOST}:{MQTT_PORT}")
    print()
    print("   📡 API ENDPOINTS v7.0:")
    print("   GET  /api/violations           — Danh sách violations (filter/paging)")
    print("   GET  /api/violations/latest    — 10 violations mới nhất (polling)")
    print("   GET  /api/device-status        — Trạng thái device + heartbeat")
    print("   POST /api/upload-violation     — Upload ảnh từ camera thật")
    print("   POST /api/violations/<id>/replace-plate-image — Thay ảnh license plate")
    print("   PUT  /api/violations/<id>      — Sửa license plate (admin Level 3)")
    print("   GET  /api/violations/export    — Xuất CSV")
    print()


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _bootstrap()
    socketio.run(
        app,
        host="0.0.0.0",
        port=5050,
        debug=False,
        use_reloader=False,
        log_output=True,
        allow_unsafe_werkzeug=True,
    )
