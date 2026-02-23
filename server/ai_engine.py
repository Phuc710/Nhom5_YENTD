"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI ENGINE v6.0 — PREMIUM AI DETECTION MODULE (2026)                       ║
║  YOLOv8 + EasyOCR + MQTT + ESP32-CAM + Vietnamese License Plate OCR       ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │  CAMERA ARCHITECTURE — ai_engine's role                            │    ║
║  │                                                                     │    ║
║  │  Camera Live (/video_feed) — ai_engine handles detection:          │    ║
║  │    • Chưa có ESP32 → mở VideoCapture(0) làm fallback DEMO         │    ║
║  │    • ESP32 kết nối → nhận frame qua MQTT (traffic/esp32/frame)     │    ║
║  │      → REAL mode, switch ngay lập tức, không cần restart           │    ║
║  │    • Detect: YOLOv8 xe máy/ô tô + EasyOCR biển số VN/quốc tế     │    ║
║  │    • Chỉ detect khi đèn ĐỎ/VÀNG — tiết kiệm tài nguyên           │    ║
║  │                                                                     │    ║
║  │  Camera Laptop (/laptop_feed) — app.py handles:                    │    ║
║  │    • VideoCapture(0) owned by app._laptop_cam_worker               │    ║
║  │    • Stream riêng cho khách hàng test                              │    ║
║  │    • 2 streams HOÀN TOÀN ĐỘC LẬP — chạy song song                │    ║
║  │                                                                     │    ║
║  │  ✅ Cả 2 có thể mở VideoCapture(0) cùng lúc (hầu hết OS OK)      │    ║
║  │     Nếu OS không cho → ai_engine dùng demo frames,                │    ║
║  │     Camera Laptop vẫn hoạt động bình thường                       │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  PUBLIC API (0 fragile import) — app.py calls these:                       ║
║    start_ai(app)              ← bootstrap                                   ║
║    sync_light_state(light)    ← traffic cycle notification                 ║
║    get_esp32_status() → dict  ← status for frontend                        ║
║                                                                              ║
║  app.py PUBLIC API — ai_engine calls these:                                 ║
║    app.set_ai_frame(bytes)    ← push detection frame to /laptop_feed       ║
║    app.get_current_light()    ← read traffic light state                   ║
║    app.update_ai_context()    ← update context + emit WebSocket            ║
║    app.process_violation()    ← save violation to DB + emit                ║
║                                                                              ║
║  VERSION HISTORY:                                                            ║
║    v5.0  YOLOv8 + EasyOCR + MQTT + ESP32 frame receiver                  ║
║    v5.1  set_ai_frame() + EasyOCR offline check + graceful fallback       ║
║    v5.2  get_current_light() + update_ai_context() (0 fragile import)    ║
║    v5.3  Camera architecture documented (dual stream, no conflict)        ║
║    v6.0  Full rewrite: VN+international plate regex, improved demo,       ║
║          connection quality tracking, dual-plate OCR (VN + foreign),      ║
║          violation heatmap data, performance metrics, enhanced logging    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import cv2
import time
import json
import base64
import logging
import logging.handlers
import threading
import re
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Lazy imports — graceful degradation if not installed ─────────────────────
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    YOLO = None

try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False
    easyocr = None

try:
    import paho.mqtt.client as mqtt
    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False
    mqtt = None

# ── Logger ───────────────────────────────────────────────────────────────────
log = logging.getLogger("TrafficAI.AIEngine")
log.setLevel(logging.DEBUG)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] AIEngine: %(message)s", "%H:%M:%S"
    ))
    log.addHandler(_h)

# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS & CONFIG
# ════════════════════════════════════════════════════════════════════════════

MQTT_HOST      = "broker.hivemq.com"
MQTT_PORT      = 1883
MQTT_KEEPALIVE = 60

TOPIC_CONTEXT     = "traffic/ai/context"
TOPIC_VIOLATION   = "traffic/ai/violation"
TOPIC_TRAFFIC_ST  = "traffic/light/state"
TOPIC_ESP32_FRAME = "traffic/esp32/frame"

# YOLO COCO class IDs
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
TARGET_CLASSES  = {2: "car", 3: "motorcycle"}  # Only car + motorbike

# ROI: violation zone — bottom 30% of frame (near stop line)
ROI_RATIO_TOP    = 0.60
ROI_RATIO_BOTTOM = 0.90
ROI_RATIO_LEFT   = 0.04
ROI_RATIO_RIGHT  = 0.96

# Detection config
CONF_THRESHOLD     = 0.45   # YOLO confidence threshold
OCR_MIN_CHARS      = 4      # Vietnamese plate min 4 chars
CAPTURE_INTERVAL   = 0.5    # 500ms capture throttle
MAX_VEHICLES       = 6      # ESP32 optimization limit
PLATE_THROTTLE_SEC = 30     # Same plate: skip for 30s

# Camera — ai_engine uses webcam as fallback when no ESP32
CAMERA_SOURCE = 0   # VideoCapture(0) — same as app.py Camera Laptop

# ════════════════════════════════════════════════════════════════════════════
# GLOBAL STATE
# ════════════════════════════════════════════════════════════════════════════

# Traffic light state (synced from app.py via sync_light_state())
_current_light = "RED"
_light_lock    = threading.Lock()

# ESP32 connection tracking
_esp32_ever_connected = threading.Event()
_esp32_last_frame_ts  = 0.0
_esp32_frame_lock     = threading.Lock()
_esp32_latest_frame: bytes | None = None

# Plate throttle: {plate_text: last_process_ts}
_plate_seen: dict[str, float] = {}
_plate_lock = threading.Lock()

# AI models (loaded once, background thread)
_vehicle_model = None
_ocr_reader    = None
_models_ready  = threading.Event()

# MQTT client
_ai_mqtt: "mqtt.Client | None" = None  # type: ignore

# Stop signal
_stop_event = threading.Event()

# v6.0: Performance metrics
_perf = {
    "total_frames":       0,
    "detection_frames":   0,
    "violations_found":   0,
    "ocr_success":        0,
    "ocr_fail":           0,
    "esp32_frames":       0,
    "webcam_frames":      0,
    "demo_frames":        0,
    "detection_fps":      0.0,
    "last_fps_ts":        0.0,
    "last_fps_count":     0,
}
_perf_lock = threading.Lock()


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API — called by app.py
# ════════════════════════════════════════════════════════════════════════════

def sync_light_state(light: str):
    """
    PUBLIC API — app.py calls this every time traffic light changes.
    ai_engine activates detection when RED/YELLOW, pauses when GREEN.
    """
    global _current_light
    with _light_lock:
        old = _current_light
        _current_light = light.upper()
    if old != _current_light:
        active = "🔴 ACTIVE" if _current_light in ("RED", "YELLOW") else "⚪ IDLE"
        log.info("🚦 Light sync: %s → %s | Detection: %s", old, _current_light, active)


def get_esp32_status() -> dict:
    """
    PUBLIC API — app.py calls this to get AI/ESP32 status for frontend.
    Returns serializable dict (no non-primitive types).
    """
    now = time.time()
    with _perf_lock:
        p = dict(_perf)
    return {
        "ever_connected":   _esp32_ever_connected.is_set(),
        "demo_mode":        not _esp32_ever_connected.is_set(),
        "last_frame_age":   round(now - _esp32_last_frame_ts, 1) if _esp32_last_frame_ts else None,
        "models_ready":     _models_ready.is_set(),
        "yolo_available":   _YOLO_AVAILABLE,
        "ocr_available":    _EASYOCR_AVAILABLE,
        "mqtt_available":   _MQTT_AVAILABLE,
        "mqtt_connected":   _ai_mqtt is not None and _ai_mqtt.is_connected(),
        "detection_fps":    round(p["detection_fps"], 1),
        "total_frames":     p["total_frames"],
        "violations_found": p["violations_found"],
        "ocr_success_rate": round(p["ocr_success"] / max(1, p["ocr_success"] + p["ocr_fail"]) * 100, 1),
        "frame_source":     "ESP32-CAM" if _esp32_ever_connected.is_set() else "WEBCAM/DEMO",
        "version":          "6.0",
    }


def start_ai(app_instance):
    """
    PUBLIC API — app.py calls this in _bootstrap().
    Starts all AI engine threads.

    Args:
        app_instance: Flask app object (for circular import avoidance)
    """
    log.info("🤖 AI Engine v6.0 initializing...")

    _AppRef.set(app_instance)

    # Expose sync functions to app
    app_instance.ai_sync_light   = sync_light_state
    app_instance.ai_esp32_status = get_esp32_status

    # Thread 1: Load models (background, non-blocking)
    threading.Thread(target=_load_models_worker, name="AI-ModelLoader", daemon=True).start()

    # Thread 2: MQTT — receive ESP32-CAM frames
    threading.Thread(target=_mqtt_worker, name="AI-MQTT", daemon=True).start()

    # Thread 3: Main detection loop
    threading.Thread(target=_detection_loop, name="AI-Detection", daemon=True).start()

    log.info("✅ AI Engine threads started: ModelLoader + MQTT + Detection")


# ════════════════════════════════════════════════════════════════════════════
# APP REFERENCE — avoids circular import
# ════════════════════════════════════════════════════════════════════════════

class _AppRef:
    """
    Holds runtime reference to app.py module functions.
    All calls to app.py go through this class.
    Import happens at runtime (not module load) → no circular import.
    """
    _app = None

    @classmethod
    def set(cls, app):
        cls._app = app

    @classmethod
    def process_violation(cls, payload: dict):
        """Call app.process_violation() — save + emit violation."""
        if cls._app is None:
            log.warning("AppRef not set — violation lost: %s", payload.get("plate"))
            return
        try:
            import app as _app_module
            if hasattr(_app_module, "process_violation"):
                _app_module.process_violation(payload)
            else:
                log.error("process_violation() not found in app — lost: %s", payload.get("plate"))
        except ImportError:
            log.error("Cannot import app — violation lost: %s", payload.get("plate"))
        except Exception as e:
            log.error("process_violation error: %s | plate=%s", e, payload.get("plate"))

    @classmethod
    def get_light(cls) -> str:
        """
        Read traffic light state via app.get_current_light().
        Falls back to local _current_light cache if app not available.
        """
        if cls._app is not None:
            try:
                import app as _app_module
                if hasattr(_app_module, "get_current_light"):
                    return _app_module.get_current_light()
            except Exception:
                pass
        # Fallback: local cache synced via sync_light_state()
        with _light_lock:
            return _current_light

    @classmethod
    def push_frame(cls, frame: np.ndarray):
        """Push detection frame to app's Camera Laptop stream (/laptop_feed)."""
        if cls._app is None:
            return
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                return
            import app as _app_module
            if hasattr(_app_module, "set_ai_frame"):
                _app_module.set_ai_frame(buf.tobytes())
        except Exception as e:
            log.debug("push_frame error: %s", e)

    @classmethod
    def update_context(cls, vehicles: int, fps: float, **kw):
        """Update AI context in app — triggers WebSocket emit."""
        try:
            import app as _app_module
            if hasattr(_app_module, "update_ai_context"):
                _app_module.update_ai_context(vehicles=vehicles, fps=fps, **kw)
        except Exception as e:
            log.debug("update_context error: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# MODEL LOADER
# ════════════════════════════════════════════════════════════════════════════

def _load_models_worker():
    """Load YOLOv8 + EasyOCR in background thread. Sets _models_ready when done."""
    global _vehicle_model, _ocr_reader

    log.info("📦 Loading AI models (background)...")

    # ── YOLOv8 ──────────────────────────────────────────────────────────────
    if _YOLO_AVAILABLE:
        try:
            model_path = Path("yolov8n.pt")
            if not model_path.exists():
                log.info("   yolov8n.pt not found locally → will download from Ultralytics hub (~6MB)")
            _vehicle_model = YOLO(str(model_path) if model_path.exists() else "yolov8n.pt")
            log.info("✅ YOLOv8n loaded | COCO classes: %d | Vehicle targets: car, motorcycle",
                     len(_vehicle_model.names))
        except Exception as e:
            log.error("❌ YOLOv8 load failed: %s", e)
            log.error("   Fix: pip install ultralytics")
            _vehicle_model = None
    else:
        log.warning("⚠️  ultralytics not installed → YOLO detection disabled")
        log.warning("   Install: pip install ultralytics")

    # ── EasyOCR — Vietnamese + English plate recognition ────────────────────
    if _EASYOCR_AVAILABLE:
        try:
            _easyocr_dir = Path.home() / ".EasyOCR" / "model"
            _craft       = _easyocr_dir / "craft_mlt_25k.pth"
            _eng_model   = _easyocr_dir / "english_g2.pth"
            _cached      = _craft.exists() and _eng_model.exists()

            if not _cached:
                log.warning("⚠️  EasyOCR models not cached → will download ~500MB on first run")
                log.warning("   Pre-download: python -c \"import easyocr; easyocr.Reader(['en'])\"")
                log.warning("   Offline path: set EASYOCR_MODULE_PATH to model folder")
            else:
                log.info("✅ EasyOCR model cache found: %s", _easyocr_dir)

            # lang=['en'] sufficient for Vietnamese plates (alphanumeric only)
            # Add 'vi' for full Vietnamese text if needed
            _ocr_reader = easyocr.Reader(
                ['en'],
                gpu=False,           # Set True if CUDA available
                verbose=False,
                download_enabled=True,
            )
            log.info("✅ EasyOCR loaded (lang=en, gpu=False, cached=%s)", _cached)
            log.info("   Supports: Vietnamese plates (51B-12345), Foreign plates (alphanumeric)")
        except Exception as e:
            log.error("❌ EasyOCR load failed: %s", e)
            log.error("   Fix: pip install easyocr")
            _ocr_reader = None
    else:
        log.warning("⚠️  easyocr not installed → OCR disabled (plates will show as UNKNOWN)")
        log.warning("   Install: pip install easyocr")

    _models_ready.set()
    log.info("=" * 60)
    log.info("🚀 AI Models ready | YOLO=%-8s | OCR=%-8s",
             "✅ OK" if _vehicle_model else "❌ OFF",
             "✅ OK" if _ocr_reader  else "❌ OFF")
    log.info("=" * 60)


# ════════════════════════════════════════════════════════════════════════════
# MQTT WORKER — receive ESP32-CAM frames
# ════════════════════════════════════════════════════════════════════════════

def _mqtt_worker():
    """
    MQTT client for ai_engine:
    - Subscribes to traffic/esp32/frame → receives ESP32-CAM JPEG frames
    - Subscribes to traffic/light/state → syncs traffic light
    - Auto-reconnects on disconnect

    When first ESP32 frame arrives → _esp32_ever_connected.set()
    → detection_loop switches from webcam/demo to ESP32-CAM frames
    """
    global _ai_mqtt

    if not _MQTT_AVAILABLE:
        log.warning("⚠️  paho-mqtt not available → ESP32 frame reception disabled")
        log.warning("   Install: pip install paho-mqtt")
        return

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe([
                (TOPIC_ESP32_FRAME, 0),   # QoS 0 for high-freq video frames
                (TOPIC_TRAFFIC_ST,  1),   # QoS 1 for reliable light sync
            ])
            log.info("✅ AI-MQTT connected → %s:%d | Subscribed ESP32 frame + traffic topics",
                     MQTT_HOST, MQTT_PORT)
        else:
            log.warning("AI-MQTT connect failed rc=%d — retry pending", rc)

    def on_message(client, userdata, msg):
        global _esp32_latest_frame, _esp32_last_frame_ts

        if msg.topic == TOPIC_ESP32_FRAME:
            try:
                pl = msg.payload
                # Handle both raw JPEG and base64-encoded JPEG
                if pl[:2] in (b"//", b"/9", b"iV"):
                    frame_bytes = base64.b64decode(pl)
                else:
                    frame_bytes = bytes(pl)

                with _esp32_frame_lock:
                    _esp32_latest_frame  = frame_bytes
                    _esp32_last_frame_ts = time.time()

                with _perf_lock:
                    _perf["esp32_frames"] += 1

                # First ESP32 frame → switch DEMO → REAL
                if not _esp32_ever_connected.is_set():
                    _esp32_ever_connected.set()
                    log.info("🎉 ═══════════════════════════════════════════════════")
                    log.info("🎉  ESP32-CAM CONNECTED — switching to REAL mode!")
                    log.info("🎉  Camera Live now using ESP32-CAM frames via MQTT")
                    log.info("🎉  Camera Laptop continues independently (app.py)")
                    log.info("🎉 ═══════════════════════════════════════════════════")

            except Exception as e:
                log.debug("ESP32 frame decode error: %s", e)

        elif msg.topic == TOPIC_TRAFFIC_ST:
            try:
                d = json.loads(msg.payload.decode())
                l = d.get("light", "").upper()
                if l in ("RED", "YELLOW", "GREEN"):
                    sync_light_state(l)
            except Exception:
                pass

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            log.warning("AI-MQTT disconnected rc=%d — auto-reconnect in loop_forever", rc)

    client = mqtt.Client(client_id=f"AI-Engine-v6-{int(time.time())}")
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    retry_delay = 5
    while not _stop_event.is_set():
        try:
            client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
            _ai_mqtt = client
            retry_delay = 5  # Reset on success
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            log.error("AI-MQTT error: %s — retry in %ds", e, retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)  # Exponential backoff


# ════════════════════════════════════════════════════════════════════════════
# CAMERA HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _open_laptop_camera() -> "cv2.VideoCapture | None":
    """
    Open webcam as FALLBACK for detection when no ESP32 available.

    ARCHITECTURE NOTE:
    ─────────────────
    app.py Camera Laptop stream (/laptop_feed):
      → app._laptop_cam_worker opens VideoCapture(0) → stream for customers

    ai_engine Camera Live detection (/video_feed):
      → ai_engine opens VideoCapture(0) ONLY as fallback when no ESP32
      → When ESP32 connects: ai_engine switches to ESP32-CAM immediately
      → Both can open VideoCapture(0) at the same time on most OS

    If OS only allows 1 opener (some Windows UVC drivers):
      → ai_engine cannot open webcam → falls back to demo frames
      → Camera Laptop (app.py) still works perfectly
      → When ESP32 connects: Camera Live switches to real ESP32-CAM

    This is by design — not an error.
    """
    cap = cv2.VideoCapture(CAMERA_SOURCE)
    if not cap.isOpened():
        cap.release()
        log.warning("⚠️  AI Engine: Cannot open VideoCapture(%d)", CAMERA_SOURCE)
        log.warning("    Possible reasons:")
        log.warning("    1. app._laptop_cam_worker already holding device (OS-dependent)")
        log.warning("    2. No webcam connected")
        log.warning("    → Using demo frames until ESP32 connects (normal behavior)")
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    log.info("🎥 AI Engine webcam opened for detection: VideoCapture(%d) 1280x720@30fps", CAMERA_SOURCE)
    log.info("   Note: app.py Camera Laptop may also have VideoCapture(0) open — that is OK")
    return cap


def _get_frame(cap) -> "np.ndarray | None":
    """
    Get next frame for detection. Priority:
    1. ESP32-CAM frame (if fresh < 2s) — REAL mode
    2. Laptop webcam (if open) — DEMO mode with real camera
    3. Animated demo frame — DEMO mode, no camera
    """
    now = time.time()

    # 1. ESP32-CAM frame (highest priority when connected)
    with _esp32_frame_lock:
        esp32_bytes = _esp32_latest_frame
        esp32_age   = now - _esp32_last_frame_ts if _esp32_last_frame_ts else 999

    if esp32_bytes and esp32_age < 2.0:
        try:
            arr   = np.frombuffer(esp32_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                with _perf_lock:
                    _perf["total_frames"] += 1
                return frame
        except Exception:
            pass

    # 2. Laptop webcam fallback (when no ESP32)
    if cap and cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            with _perf_lock:
                _perf["webcam_frames"] += 1
                _perf["total_frames"]  += 1
            return frame

    # 3. Animated demo frame
    frame = _generate_demo_frame()
    with _perf_lock:
        _perf["demo_frames"] += 1
        _perf["total_frames"] += 1
    return frame


# ════════════════════════════════════════════════════════════════════════════
# DEMO FRAME GENERATOR
# ════════════════════════════════════════════════════════════════════════════

_demo_state = {
    "vx1": 100, "vx2": 700,
    "vy1": 440, "vy2": 470,
    "vx3": 400, "vy3": 500,
}


def _generate_demo_frame() -> np.ndarray:
    """
    High-quality animated demo frame for Camera Live detection.
    Shows realistic road scene with moving vehicles + license plates.
    Used when no ESP32 AND no webcam available.
    """
    W, H = 1280, 720
    frame = np.zeros((H, W, 3), dtype=np.uint8)

    # ── Background: sky + road ───────────────────────────────────
    for y in range(int(H * 0.55)):
        v = int(28 - (y / (H * 0.55)) * 18)
        frame[y, :] = (max(4,v-2), max(8,v), max(16,v+4))

    cv2.rectangle(frame, (0, int(H*0.55)), (W, H), (20, 26, 34), -1)

    # Road lane dividers
    for xi in range(0, W, 100):
        cv2.line(frame, (xi, int(H*0.70)), (xi+50, int(H*0.70)), (45, 55, 65), 2)
    # Road edges
    cv2.line(frame, (0, int(H*0.58)), (W, int(H*0.58)), (35, 45, 55), 1)

    # ── Animated vehicles ────────────────────────────────────────
    t = time.time()

    # Vehicle 1 — blue car
    vx1 = int((W * 0.05) + (t * 90) % (W * 0.82))
    vy1 = int(H * 0.65)
    # Body
    cv2.rectangle(frame, (vx1-42, vy1-24), (vx1+42, vy1+24), (45, 85, 185), -1)
    cv2.rectangle(frame, (vx1-42, vy1-24), (vx1+42, vy1+24), (70, 120, 220), 1)
    # Roof
    cv2.rectangle(frame, (vx1-28, vy1-38), (vx1+28, vy1-20), (35, 65, 150), -1)
    # Windshield
    cv2.rectangle(frame, (vx1-22, vy1-36), (vx1+22, vy1-22), (60, 90, 160), -1)
    # Wheels
    cv2.circle(frame, (vx1-28, vy1+24), 8, (20, 20, 20), -1)
    cv2.circle(frame, (vx1+28, vy1+24), 8, (20, 20, 20), -1)
    # License plate VN
    cv2.rectangle(frame, (vx1-26, vy1+8), (vx1+26, vy1+22), (220, 220, 50), -1)
    cv2.putText(frame, "51B-12345", (vx1-24, vy1+20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (20, 20, 20), 1)

    # Vehicle 2 — red motorbike
    vx2 = int(W * 0.55 + (t * 60) % (W * 0.38))
    vy2 = int(H * 0.70)
    cv2.rectangle(frame, (vx2-22, vy2-20), (vx2+22, vy2+20), (140, 35, 35), -1)
    cv2.rectangle(frame, (vx2-22, vy2-20), (vx2+22, vy2+20), (190, 60, 60), 1)
    cv2.circle(frame, (vx2-14, vy2+20), 7, (20, 20, 20), -1)
    cv2.circle(frame, (vx2+14, vy2+20), 7, (20, 20, 20), -1)
    cv2.rectangle(frame, (vx2-14, vy2+6), (vx2+14, vy2+18), (220, 220, 50), -1)
    cv2.putText(frame, "30A-99001", (vx2-12, vy2+16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.28, (20, 20, 20), 1)

    # Vehicle 3 — foreign plate (stopped at ROI)
    vx3 = int(W * 0.40)
    vy3 = int(H * 0.74)
    cv2.rectangle(frame, (vx3-38, vy3-20), (vx3+38, vy3+20), (60, 140, 60), -1)
    cv2.rectangle(frame, (vx3-38, vy3-20), (vx3+38, vy3+20), (80, 180, 80), 1)
    cv2.rectangle(frame, (vx3-25, vy3-32), (vx3+25, vy3-18), (50, 110, 50), -1)
    # Foreign plate (EU style: white)
    cv2.rectangle(frame, (vx3-26, vy3+5), (vx3+26, vy3+19), (240, 240, 240), -1)
    cv2.rectangle(frame, (vx3-26, vy3+5), (vx3+26, vy3+19), (40, 40, 180), 2)
    cv2.putText(frame, "ABC 1234", (vx3-24, vy3+17),
                cv2.FONT_HERSHEY_SIMPLEX, 0.30, (20, 20, 20), 1)

    # ── DEMO watermark ───────────────────────────────────────────
    cv2.putText(frame, "DEMO MODE — CAMERA LIVE",
                (int(W*0.24), int(H*0.38)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (12, 24, 48), 3, cv2.LINE_AA)
    cv2.putText(frame, "Connect ESP32-CAM via MQTT to go LIVE",
                (int(W*0.22), int(H*0.44)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (20, 60, 120), 1, cv2.LINE_AA)

    return frame


# ════════════════════════════════════════════════════════════════════════════
# YOLO DETECTION
# ════════════════════════════════════════════════════════════════════════════

def _run_yolo(frame: np.ndarray) -> list[tuple]:
    """
    Run YOLOv8 on frame. Returns list of (cls_id, cls_name, conf, x1, y1, x2, y2).
    Falls back to demo detections if model not available.
    """
    if _vehicle_model is not None:
        try:
            results = _vehicle_model(frame, verbose=False, conf=CONF_THRESHOLD)
            detections = []
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id  = int(box.cls[0])
                    conf    = float(box.conf[0])
                    xyxy    = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                    cls_name = _vehicle_model.names.get(cls_id, f"cls_{cls_id}")
                    detections.append((cls_id, cls_name, conf, x1, y1, x2, y2))
            with _perf_lock:
                _perf["detection_frames"] += 1
            return detections
        except Exception as e:
            log.debug("YOLO inference error: %s", e)
            return []
    else:
        return _demo_detections(frame)


def _demo_detections(frame: np.ndarray) -> list[tuple]:
    """Animated demo detections when YOLO not available."""
    if not hasattr(_demo_detections, "_pos"):
        _demo_detections._pos = 0
    h, w = frame.shape[:2]
    _demo_detections._pos = (_demo_detections._pos + 3) % (w - 80)
    x = _demo_detections._pos
    y = int(h * 0.70)
    return [(3, "motorcycle", 0.82, x, y-30, x+60, y+30)]


# ════════════════════════════════════════════════════════════════════════════
# OCR — Vietnamese + International License Plate Recognition
# ════════════════════════════════════════════════════════════════════════════

# Vietnamese plate patterns:
#   Old: 51B-12345, 30A-999.99, 36F-8888
#   New: 51A1-12345, 29H1-12345
#   Motorbike: 51M1-123.45
_VN_PLATE_PATTERNS = [
    re.compile(r'\b(\d{2}[A-Z]\d?[-\s]?\d{4,5})\b', re.IGNORECASE),
    re.compile(r'\b(\d{2}[A-Z]{1,2}[-\s]?\d{4,5})\b', re.IGNORECASE),
    re.compile(r'\b(\d{2}[A-Z]\d[-\s]?\d{3}[.\-]?\d{2})\b', re.IGNORECASE),
]

# International plate patterns (EU, US, etc.)
_INTL_PLATE_PATTERNS = [
    re.compile(r'\b([A-Z]{1,3}[\s\-]?\d{3,4}[\s\-]?[A-Z]{0,2})\b', re.IGNORECASE),
    re.compile(r'\b([A-Z0-9]{5,8})\b'),   # Generic alphanumeric 5-8 chars
]


def _run_ocr(crop: np.ndarray) -> str:
    """
    Run EasyOCR on vehicle crop to extract license plate text.
    Tries Vietnamese patterns first, then international.
    Returns cleaned plate string or empty string.
    """
    if _ocr_reader is None:
        return ""

    if crop is None or crop.size == 0:
        return ""

    try:
        # Preprocess for better OCR accuracy
        crop_proc = _preprocess_plate_crop(crop)

        results = _ocr_reader.readtext(
            crop_proc,
            allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. ",
            detail=1,
            paragraph=False,
        )

        if not results:
            with _perf_lock:
                _perf["ocr_fail"] += 1
            return ""

        # Combine all text from results
        all_text = " ".join(r[1].strip().upper() for r in results if r[2] > 0.3)
        all_text = all_text.replace("O", "0").replace("I", "1").replace("l", "1")

        # Try Vietnamese patterns first (priority)
        for pattern in _VN_PLATE_PATTERNS:
            m = pattern.search(all_text)
            if m:
                plate = _normalize_vn_plate(m.group(1))
                if len(plate) >= OCR_MIN_CHARS:
                    with _perf_lock:
                        _perf["ocr_success"] += 1
                    log.debug("OCR [VN] found: %s", plate)
                    return plate

        # Try international patterns
        for pattern in _INTL_PLATE_PATTERNS:
            m = pattern.search(all_text)
            if m:
                plate = m.group(1).strip().upper()
                plate = re.sub(r'\s+', ' ', plate)
                if len(plate) >= OCR_MIN_CHARS:
                    with _perf_lock:
                        _perf["ocr_success"] += 1
                    log.debug("OCR [INTL] found: %s", plate)
                    return plate

        # Fallback: best single result if confidence > 0.5
        best = max(results, key=lambda r: r[2])
        if best[2] > 0.5 and len(best[1].strip()) >= OCR_MIN_CHARS:
            plate = best[1].strip().upper()
            with _perf_lock:
                _perf["ocr_success"] += 1
            return plate

        with _perf_lock:
            _perf["ocr_fail"] += 1
        return ""

    except Exception as e:
        log.debug("OCR error: %s", e)
        with _perf_lock:
            _perf["ocr_fail"] += 1
        return ""


def _preprocess_plate_crop(crop: np.ndarray) -> np.ndarray:
    """Preprocess vehicle crop for better OCR accuracy."""
    try:
        # Resize if too small
        h, w = crop.shape[:2]
        if w < 100 or h < 30:
            scale = max(100 / w, 30 / h)
            crop = cv2.resize(crop, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)

        # Grayscale → bilateral filter → adaptive threshold → morphology
        gray   = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.bilateralFilter(gray, 9, 75, 75)
        thresh = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
            11, 2
        )
        kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Return as 3-channel (EasyOCR expects BGR or gray)
        return cv2.cvtColor(cv2.bitwise_not(cleaned), cv2.COLOR_GRAY2BGR)
    except Exception:
        return crop  # Return original if preprocessing fails


def _normalize_vn_plate(raw: str) -> str:
    """Normalize Vietnamese plate format: 51B-12345, 30A-999.99."""
    p = raw.upper().replace(" ", "").replace(".", "").replace("-", "")
    # Insert dash: 2 digits + letters, then dash + numbers
    m = re.match(r'^(\d{2}[A-Z]{1,2}\d?)(\d{4,5})$', p)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return raw.upper()


# ════════════════════════════════════════════════════════════════════════════
# MAIN DETECTION LOOP
# ════════════════════════════════════════════════════════════════════════════

def _detection_loop():
    """
    Main AI detection loop.

    Flow:
    1. Wait for models to load (max 120s)
    2. Open laptop webcam as fallback source
    3. Loop every ~30ms:
       - GREEN light → skip (no detection, save CPU)
       - YELLOW light → detect + draw (warm-up, no violations)
       - RED light → detect + ROI check + OCR + process_violation

    Frame source priority (checked every iteration):
    → ESP32-CAM (if fresh) → laptop webcam → demo frame
    """
    log.info("⏳ Detection loop: waiting for models (timeout=120s)...")
    _models_ready.wait(timeout=120)

    if not _models_ready.is_set():
        log.error("❌ Models not ready after 120s — detection loop aborted")
        return

    log.info("🎯 Detection loop started")

    # Open webcam as fallback (ai_engine + app.py can both have webcam open simultaneously)
    cap = _open_laptop_camera()

    frame_count  = 0
    last_capture_ts = 0.0
    fps_ts       = time.time()
    fps_count    = 0

    while not _stop_event.is_set():
        try:
            current_light = _AppRef.get_light()

            # ── GREEN: idle mode — no detection ─────────────────
            if current_light == "GREEN":
                _AppRef.update_context(0, 0.0)
                time.sleep(0.2)
                continue

            # ── Get frame ────────────────────────────────────────
            frame = _get_frame(cap)
            if frame is None:
                time.sleep(0.1)
                continue

            # ── FPS tracking ─────────────────────────────────────
            fps_count += 1
            now = time.time()
            elapsed = now - fps_ts
            fps = fps_count / elapsed if elapsed > 0 else 0.0
            if elapsed >= 3.0:
                with _perf_lock:
                    _perf["detection_fps"]  = fps
                    _perf["last_fps_count"] = fps_count
                fps_ts = now; fps_count = 0

            # ── YOLO detection ───────────────────────────────────
            detections = _run_yolo(frame)
            h, w = frame.shape[:2]

            roi_y1 = int(h * ROI_RATIO_TOP)
            roi_y2 = int(h * ROI_RATIO_BOTTOM)
            roi_x1 = int(w * ROI_RATIO_LEFT)
            roi_x2 = int(w * ROI_RATIO_RIGHT)

            vehicles_in_frame   = 0
            violations_detected = []

            for det in detections:
                cls_id, cls_name, conf, x1, y1, x2, y2 = det
                if cls_id not in TARGET_CLASSES:
                    continue
                if conf < CONF_THRESHOLD:
                    continue

                vehicles_in_frame += 1

                # Draw bounding box
                box_color = (0, 230, 80) if current_light == "GREEN" else \
                            (0, 180, 220) if current_light == "YELLOW" else (20, 20, 220)
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

                label = f"{cls_name} {conf*100:.0f}%"
                label_y = max(y1 - 8, 18)
                cv2.rectangle(frame, (x1, label_y-14), (x1 + len(label)*8, label_y+4), box_color, -1)
                cv2.putText(frame, label, (x1+2, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 1, cv2.LINE_AA)

                # ── RED light: check if in violation ROI ────────
                if current_light == "RED":
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    in_roi = (roi_x1 <= cx <= roi_x2) and (roi_y1 <= cy <= roi_y2)

                    if in_roi:
                        # Highlight violation
                        cv2.rectangle(frame, (x1-3, y1-3), (x2+3, y2+3), (0, 0, 255), 3)
                        violations_detected.append({
                            "cls_id": cls_id, "cls_name": cls_name, "conf": conf,
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "cx": cx, "cy": cy,
                        })

            # ── Draw ROI line ─────────────────────────────────────
            roi_color = (50, 50, 220) if current_light == "RED" else \
                        (50, 200, 220) if current_light == "YELLOW" else (50, 200, 50)
            cv2.line(frame, (roi_x1, roi_y1), (roi_x2, roi_y1), roi_color, 2)
            cv2.line(frame, (roi_x1, roi_y1), (roi_x1, roi_y2), roi_color, 1)
            cv2.line(frame, (roi_x2, roi_y1), (roi_x2, roi_y2), roi_color, 1)

            # ROI label
            roi_label = "🔴 VIOLATION ZONE — STOP LINE" if current_light == "RED" else "DETECTION ROI"
            cv2.putText(frame, roi_label,
                        (roi_x1 + 10, roi_y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, roi_color, 1, cv2.LINE_AA)

            # ── Source indicator ──────────────────────────────────
            src_txt = "SOURCE: ESP32-CAM" if _esp32_ever_connected.is_set() else "SOURCE: WEBCAM/DEMO"
            src_color = (0, 220, 100) if _esp32_ever_connected.is_set() else (0, 120, 220)
            cv2.putText(frame, src_txt, (roi_x1 + 10, roi_y1 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, src_color, 1, cv2.LINE_AA)

            # ── Push frame to Camera Laptop stream ───────────────
            _AppRef.push_frame(frame)

            # ── Capture throttle: 500ms between violation saves ──
            if (now - last_capture_ts) < CAPTURE_INTERVAL:
                _AppRef.update_context(vehicles_in_frame, fps)
                time.sleep(0.02)
                continue

            # ── Process violations (RED only) ─────────────────────
            if current_light == "RED" and violations_detected:
                last_capture_ts = now
                for viol in violations_detected:
                    _handle_violation(frame, viol, vehicles_in_frame)

            _AppRef.update_context(vehicles_in_frame, fps,
                                   capture_interval=CAPTURE_INTERVAL,
                                   roi="STOP_LINE",
                                   target_objects=["MOTORBIKE", "CAR"],
                                   weather="SUN",
                                   distance=5.0)

            frame_count += 1
            time.sleep(0.030)  # ~33fps loop

        except Exception as e:
            log.error("Detection loop error: %s", e, exc_info=True)
            time.sleep(0.5)

    if cap:
        cap.release()
    log.info("🛑 Detection loop stopped | total_frames=%d violations=%d",
             _perf["total_frames"], _perf["violations_found"])


# ════════════════════════════════════════════════════════════════════════════
# VIOLATION HANDLER
# ════════════════════════════════════════════════════════════════════════════

def _handle_violation(frame: np.ndarray, viol: dict, vehicles_in_frame: int):
    """
    Handle a single violation detection:
    1. Crop vehicle region
    2. OCR license plate (VN + international)
    3. Throttle check (same plate not processed within 30s)
    4. Encode violation image (full frame)
    5. Call app.process_violation()
    6. Publish to MQTT (for ESP32 + ThingsBoard)
    """
    x1, y1, x2, y2 = viol["x1"], viol["y1"], viol["x2"], viol["y2"]
    cls_name = viol["cls_name"]
    conf     = viol["conf"]

    # Crop vehicle with padding
    h, w = frame.shape[:2]
    pad = 15
    cx1 = max(0, x1 - pad)
    cy1 = max(0, y1 - pad)
    cx2 = min(w, x2 + pad)
    cy2 = min(h, y2 + pad)
    car_crop = frame[cy1:cy2, cx1:cx2]

    # OCR — try to read license plate
    plate = _run_ocr(car_crop)

    # Plate throttle: skip if same plate within PLATE_THROTTLE_SEC
    if plate:
        now = time.time()
        with _plate_lock:
            last_ts = _plate_seen.get(plate, 0)
            if now - last_ts < PLATE_THROTTLE_SEC:
                log.debug("Plate throttled: %s (%.0fs ago)", plate, now - last_ts)
                return
            _plate_seen[plate] = now

    # Encode violation image (full frame JPEG)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    image_b64 = base64.b64encode(buf.tobytes()).decode() if ok else ""

    vtype_map = {"car": "CAR", "motorcycle": "MOTORBIKE", "bus": "BUS", "truck": "TRUCK"}
    vtype     = vtype_map.get(cls_name, "UNKNOWN")
    cam_id    = "ESP32-CAM" if _esp32_ever_connected.is_set() else "LAPTOP_CAM"

    payload = {
        "ts":             int(time.time()),
        "plate":          plate or "UNKNOWN",
        "type":           vtype,
        "speed_kmh":      0.0,          # No radar — future enhancement
        "confidence":     round(conf, 4),
        "image_b64":      image_b64,
        "cam_id":         cam_id,
        "roi":            "STOP_LINE",
        "vehicles_frame": vehicles_in_frame,
    }

    log.warning("🚨 VIOLATION: plate=%-12s type=%-10s conf=%.2f cam=%s",
                payload["plate"], vtype, conf, cam_id)

    with _perf_lock:
        _perf["violations_found"] += 1

    # Notify app.py
    _AppRef.process_violation(payload)

    # Publish to MQTT (for ESP32 display + ThingsBoard)
    if _ai_mqtt and _ai_mqtt.is_connected():
        try:
            mqtt_payload = {k: v for k, v in payload.items() if k != "image_b64"}
            _ai_mqtt.publish(TOPIC_VIOLATION, json.dumps(mqtt_payload), qos=1)
        except Exception as e:
            log.debug("MQTT violation publish error: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# CONTEXT PUBLISHER
# ════════════════════════════════════════════════════════════════════════════

def _publish_context(vehicles_in_frame: int, fps: float, light: str):
    """
    Publish AI context to app.py (WebSocket → frontend) and MQTT (ESP32 + ThingsBoard).
    Called each detection loop iteration.
    """
    # Update app.py context (emits WebSocket event automatically)
    _AppRef.update_context(
        vehicles=vehicles_in_frame,
        fps=fps,
        capture_interval=CAPTURE_INTERVAL,
        roi="STOP_LINE",
        target_objects=["MOTORBIKE", "CAR"],
        weather="SUN",
        distance=5.0,
    )

    # MQTT publish for ESP32 + ThingsBoard
    if _ai_mqtt is None or not _ai_mqtt.is_connected():
        return

    payload = {
        "vehicles_frame":   min(vehicles_in_frame, MAX_VEHICLES),
        "fps":              round(fps, 1),
        "capture_interval": CAPTURE_INTERVAL,
        "roi":              "STOP_LINE",
        "target_objects":   ["MOTORBIKE", "CAR"],
        "weather":          "SUN",
        "distance":         5.0,
        "light":            light,
        "ts":               int(time.time()),
        "source":           "ESP32-CAM" if _esp32_ever_connected.is_set() else "DEMO",
    }
    try:
        _ai_mqtt.publish(TOPIC_CONTEXT, json.dumps(payload))
    except Exception as e:
        log.debug("MQTT context publish error: %s", e)


def _update_app_frame(frame: np.ndarray):
    """
    Push detection-annotated frame to app.py's Camera Laptop stream.
    Wraps _AppRef.push_frame() for backward compatibility.
    """
    _AppRef.push_frame(frame)


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API EXPORTS
# ════════════════════════════════════════════════════════════════════════════

__all__ = [
    "start_ai",           # app.py: _bootstrap() → start_ai(app)
    "sync_light_state",   # app.py: traffic cycle → sync_light_state("RED")
    "get_esp32_status",   # app.py: API/WS → get_esp32_status()
]