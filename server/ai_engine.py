"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI ENGINE v6.1 — FIXED CAMERA ARCHITECTURE                                ║
║                                                                              ║
║  KIẾN TRÚC CAMERA (TÁCH BIỆT HOÀN TOÀN):                                  ║
║                                                                              ║
║  ┌─ Camera Live (/video_feed) ─────────────────────────────────────────┐   ║
║  │  Quản lý bởi: ai_engine.py                                          │   ║
║  │  Nguồn frame: MQTT topic traffic/esp32/frame (từ ESP32-CAM)         │   ║
║  │  Khi CHƯA có ESP32: hiển thị demo frame bằng OpenCV (KHÔNG mở      │   ║
║  │                      VideoCapture, KHÔNG bật đèn camera)            │   ║
║  │  Khi CÓ ESP32:       decode JPEG từ MQTT → YOLO detect → push frame │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
║                                                                              ║
║  ┌─ Camera Laptop (/laptop_feed) ──────────────────────────────────────┐   ║
║  │  Quản lý bởi: app.py (_laptop_cam_worker)                           │   ║
║  │  Nguồn frame: VideoCapture(0) — webcam laptop                       │   ║
║  │  Chỉ mở khi: user nhấn nút "Bật Camera" trên web                   │   ║
║  │  ai_engine KHÔNG BAO GIỜ mở VideoCapture hoặc tương tác với module  │   ║
║  │  này.                                                                │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
║                                                                              ║
║  PUBLIC API mà app.py gọi:                                                  ║
║    start_ai(app)           — bootstrap từ _bootstrap()                      ║
║    sync_light_state(light) — traffic cycle thông báo đèn thay đổi          ║
║    get_esp32_status()      — trả về dict trạng thái cho frontend            ║
║                                                                              ║
║  app.py PUBLIC API mà ai_engine gọi:                                        ║
║    app.set_ai_frame(bytes) — push frame detection lên /video_feed           ║
║    app.get_current_light() — đọc trạng thái đèn                            ║
║    app.update_ai_context() — cập nhật context + emit WebSocket             ║
║    app.process_violation() — lưu vi phạm vào DB + emit                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import cv2
import time
import json
import base64
import logging
import threading
import re
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Lazy imports — graceful degradation ──────────────────────────────────────
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

# ── Logger ────────────────────────────────────────────────────────────────────
log = logging.getLogger("TrafficAI.AIEngine")
log.setLevel(logging.DEBUG)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] AIEngine: %(message)s", "%H:%M:%S"
    ))
    log.addHandler(_h)

# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════════════════

MQTT_HOST      = "broker.hivemq.com"
MQTT_PORT      = 1883
MQTT_KEEPALIVE = 60

TOPIC_CONTEXT     = "traffic/ai/context"
TOPIC_VIOLATION   = "traffic/ai/violation"
TOPIC_TRAFFIC_ST  = "traffic/light/state"
TOPIC_ESP32_FRAME = "traffic/esp32/frame"

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
TARGET_CLASSES  = {2: "car", 3: "motorcycle"}

ROI_RATIO_TOP    = 0.60
ROI_RATIO_BOTTOM = 0.90
ROI_RATIO_LEFT   = 0.04
ROI_RATIO_RIGHT  = 0.96

CONF_THRESHOLD     = 0.45
OCR_MIN_CHARS      = 4
CAPTURE_INTERVAL   = 0.5
MAX_VEHICLES       = 6
PLATE_THROTTLE_SEC = 30

# ════════════════════════════════════════════════════════════════════════════
# GLOBAL STATE
# ════════════════════════════════════════════════════════════════════════════

_current_light = "RED"
_light_lock    = threading.Lock()

# ESP32-CAM frame buffer (nhận qua MQTT)
_esp32_ever_connected = threading.Event()
_esp32_last_frame_ts  = 0.0
_esp32_frame_lock     = threading.Lock()
_esp32_latest_frame: bytes | None = None

_plate_seen: dict[str, float] = {}
_plate_lock = threading.Lock()

_vehicle_model = None
_ocr_reader    = None
_models_ready  = threading.Event()

_ai_mqtt: "mqtt.Client | None" = None  # type: ignore
_stop_event = threading.Event()

_perf = {
    "total_frames": 0, "detection_frames": 0, "violations_found": 0,
    "ocr_success": 0, "ocr_fail": 0, "esp32_frames": 0, "demo_frames": 0,
    "detection_fps": 0.0,
}
_perf_lock = threading.Lock()


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API — app.py gọi các hàm này
# ════════════════════════════════════════════════════════════════════════════

def sync_light_state(light: str):
    """PUBLIC API — app.py gọi khi đèn thay đổi."""
    global _current_light
    with _light_lock:
        old = _current_light
        _current_light = light.upper()
    if old != _current_light:
        active = "🔴 ACTIVE" if _current_light in ("RED", "YELLOW") else "⚪ IDLE"
        log.info("🚦 Light: %s → %s | Detection: %s", old, _current_light, active)


def get_esp32_status() -> dict:
    """PUBLIC API — app.py gọi để lấy trạng thái AI/ESP32 cho frontend."""
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
        # Camera Laptop KHÔNG liên quan đến ai_engine
        "frame_source":     "ESP32-CAM" if _esp32_ever_connected.is_set() else "DEMO (no ESP32)",
        "laptop_cam":       "managed by app.py — independent",
        "version":          "6.1",
    }


def start_ai(app_instance):
    """PUBLIC API — app.py gọi trong _bootstrap()."""
    log.info("🤖 AI Engine v6.1 — Camera Live (ESP32-CAM only, no webcam)")
    _AppRef.set(app_instance)
    app_instance.ai_sync_light   = sync_light_state
    app_instance.ai_esp32_status = get_esp32_status

    threading.Thread(target=_load_models_worker, name="AI-ModelLoader", daemon=True).start()
    threading.Thread(target=_mqtt_worker,         name="AI-MQTT",        daemon=True).start()
    threading.Thread(target=_detection_loop,       name="AI-Detection",   daemon=True).start()

    log.info("✅ AI Engine threads started (ModelLoader + MQTT + Detection)")
    log.info("📌 Camera Laptop: managed by app.py independently — ai_engine will NOT touch it")


# ════════════════════════════════════════════════════════════════════════════
# APP REFERENCE — tránh circular import
# ════════════════════════════════════════════════════════════════════════════

class _AppRef:
    _app = None

    @classmethod
    def set(cls, app):
        cls._app = app

    @classmethod
    def process_violation(cls, payload: dict):
        try:
            import app as _m
            if hasattr(_m, "process_violation"):
                _m.process_violation(payload)
        except Exception as e:
            log.error("process_violation error: %s", e)

    @classmethod
    def get_light(cls) -> str:
        try:
            import app as _m
            if hasattr(_m, "get_current_light"):
                return _m.get_current_light()
        except Exception:
            pass
        with _light_lock:
            return _current_light

    @classmethod
    def push_frame(cls, frame_bytes: bytes):
        """
        Push frame JPEG bytes lên /video_feed (Camera Live — ESP32/AI).
        KHÔNG liên quan Camera Laptop (/laptop_feed).
        """
        try:
            import app as _m
            if hasattr(_m, "set_ai_frame"):
                _m.set_ai_frame(frame_bytes)
        except Exception as e:
            log.debug("push_frame error: %s", e)

    @classmethod
    def update_context(cls, vehicles: int, fps: float, **kw):
        try:
            import app as _m
            if hasattr(_m, "update_ai_context"):
                _m.update_ai_context(vehicles=vehicles, fps=fps, **kw)
        except Exception as e:
            log.debug("update_context error: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# MODEL LOADER
# ════════════════════════════════════════════════════════════════════════════

def _load_models_worker():
    global _vehicle_model, _ocr_reader
    log.info("📦 Loading AI models (background)...")

    if _YOLO_AVAILABLE:
        try:
            _vehicle_model = YOLO("yolov8n.pt")
            log.info("✅ YOLOv8n loaded")
        except Exception as e:
            log.error("❌ YOLOv8 load failed: %s | pip install ultralytics", e)
    else:
        log.warning("⚠️  ultralytics not installed → YOLO disabled | pip install ultralytics")

    if _EASYOCR_AVAILABLE:
        try:
            _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            log.info("✅ EasyOCR loaded")
        except Exception as e:
            log.error("❌ EasyOCR load failed: %s | pip install easyocr", e)
    else:
        log.warning("⚠️  easyocr not installed → OCR disabled | pip install easyocr")

    _models_ready.set()
    log.info("🚀 Models ready | YOLO=%s | OCR=%s",
             "✅" if _vehicle_model else "❌",
             "✅" if _ocr_reader  else "❌")


# ════════════════════════════════════════════════════════════════════════════
# MQTT WORKER — nhận frame từ ESP32-CAM
# ════════════════════════════════════════════════════════════════════════════

def _mqtt_worker():
    global _ai_mqtt

    if not _MQTT_AVAILABLE:
        log.warning("⚠️  paho-mqtt not installed → ESP32 frame không nhận được | pip install paho-mqtt")
        return

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe([(TOPIC_ESP32_FRAME, 0), (TOPIC_TRAFFIC_ST, 1)])
            log.info("✅ AI-MQTT connected → subscribed ESP32 frame + traffic topics")
        else:
            log.warning("AI-MQTT connect failed rc=%d", rc)

    def on_message(client, userdata, msg):
        global _esp32_latest_frame, _esp32_last_frame_ts

        if msg.topic == TOPIC_ESP32_FRAME:
            try:
                pl = msg.payload
                frame_bytes = base64.b64decode(pl) if pl[:2] in (b"//", b"/9", b"iV") else bytes(pl)

                with _esp32_frame_lock:
                    _esp32_latest_frame  = frame_bytes
                    _esp32_last_frame_ts = time.time()

                with _perf_lock:
                    _perf["esp32_frames"] += 1

                if not _esp32_ever_connected.is_set():
                    _esp32_ever_connected.set()
                    log.info("🎉 ESP32-CAM CONNECTED → Camera Live chuyển sang REAL mode")
                    log.info("🎉 Camera Laptop (app.py) tiếp tục hoạt động độc lập")
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
            log.warning("AI-MQTT disconnected rc=%d — auto-reconnect", rc)

    client = mqtt.Client(client_id=f"AI-Engine-v61-{int(time.time())}")
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    retry_delay = 5
    while not _stop_event.is_set():
        try:
            client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
            _ai_mqtt = client
            retry_delay = 5
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            log.error("AI-MQTT error: %s — retry in %ds", e, retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)


# ════════════════════════════════════════════════════════════════════════════
# FRAME SOURCE — CHỈ ESP32 hoặc DEMO (KHÔNG mở VideoCapture)
# ════════════════════════════════════════════════════════════════════════════

def _get_frame() -> "tuple[np.ndarray, str]":
    """
    Lấy frame cho Camera Live detection.

    Priority:
    1. ESP32-CAM frame qua MQTT (nếu fresh < 2s) → "ESP32"
    2. OpenCV demo frame (animated) → "DEMO"

    ⚠️  KHÔNG BAO GIỜ mở VideoCapture(0) ở đây.
    VideoCapture(0) thuộc về Camera Laptop (app.py).
    """
    now = time.time()

    # 1. ESP32-CAM (ưu tiên cao nhất)
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
                return frame, "ESP32"
        except Exception:
            pass

    # 2. Demo frame (OpenCV, KHÔNG mở camera vật lý)
    with _perf_lock:
        _perf["demo_frames"] += 1
        _perf["total_frames"] += 1
    return _generate_demo_frame(), "DEMO"


# ════════════════════════════════════════════════════════════════════════════
# DEMO FRAME — OpenCV animated (KHÔNG cần webcam)
# ════════════════════════════════════════════════════════════════════════════

def _generate_demo_frame() -> np.ndarray:
    """
    Tạo demo frame bằng OpenCV thuần.
    KHÔNG mở VideoCapture, KHÔNG bật đèn camera.
    Hiển thị trên Camera Live khi chưa có ESP32.
    """
    W, H = 1280, 720
    frame = np.zeros((H, W, 3), dtype=np.uint8)

    # Sky gradient
    for y in range(int(H * 0.55)):
        v = int(28 - (y / (H * 0.55)) * 18)
        frame[y, :] = (max(4, v-2), max(8, v), max(16, v+4))

    # Road
    cv2.rectangle(frame, (0, int(H*0.55)), (W, H), (20, 26, 34), -1)
    cv2.line(frame, (0, int(H*0.58)), (W, int(H*0.58)), (35, 45, 55), 1)

    # Lane markings
    for xi in range(0, W, 100):
        cv2.line(frame, (xi, int(H*0.70)), (xi+50, int(H*0.70)), (45, 55, 65), 2)

    # Animated vehicles (based on time)
    t = time.time()

    # Vehicle 1 — blue car
    vx1 = int((W * 0.05) + (t * 90) % (W * 0.82))
    vy1 = int(H * 0.65)
    cv2.rectangle(frame, (vx1-42, vy1-24), (vx1+42, vy1+24), (45, 85, 185), -1)
    cv2.rectangle(frame, (vx1-42, vy1-24), (vx1+42, vy1+24), (70, 120, 220), 1)
    cv2.rectangle(frame, (vx1-28, vy1-38), (vx1+28, vy1-20), (35, 65, 150), -1)
    cv2.circle(frame, (vx1-28, vy1+24), 8, (15, 15, 15), -1)
    cv2.circle(frame, (vx1+28, vy1+24), 8, (15, 15, 15), -1)
    cv2.rectangle(frame, (vx1-26, vy1+8), (vx1+26, vy1+22), (220, 220, 50), -1)
    cv2.putText(frame, "51B-12345", (vx1-24, vy1+20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (20, 20, 20), 1)

    # Vehicle 2 — red motorbike
    vx2 = int(W * 0.55 + (t * 60) % (W * 0.38))
    vy2 = int(H * 0.70)
    cv2.rectangle(frame, (vx2-22, vy2-20), (vx2+22, vy2+20), (140, 35, 35), -1)
    cv2.circle(frame, (vx2-14, vy2+20), 7, (15, 15, 15), -1)
    cv2.circle(frame, (vx2+14, vy2+20), 7, (15, 15, 15), -1)
    cv2.rectangle(frame, (vx2-14, vy2+6), (vx2+14, vy2+18), (220, 220, 50), -1)
    cv2.putText(frame, "30A-99001", (vx2-12, vy2+16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.28, (20, 20, 20), 1)

    # ROI stop line
    roi_y = int(H * 0.70)
    cv2.line(frame, (int(W*0.04), roi_y), (int(W*0.96), roi_y), (50, 50, 220), 2)
    cv2.putText(frame, "VACH DUNG - ROI - STOP LINE",
                (int(W*0.24), roi_y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 255), 1, cv2.LINE_AA)

    # Status overlay
    cv2.rectangle(frame, (0, 0), (W, 32), (0, 0, 0), -1)
    cv2.addWeighted(frame[:32], 0.6, np.zeros_like(frame[:32]), 0.4, 0, frame[:32])
    ts = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
    cv2.putText(frame, ts, (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 230, 255), 1, cv2.LINE_AA)

    # DEMO watermark
    cv2.putText(frame, "CAMERA LIVE — DEMO",
                (int(W*0.30), int(H*0.38)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (10, 20, 45), 4, cv2.LINE_AA)
    cv2.putText(frame, "CAMERA LIVE — DEMO",
                (int(W*0.30), int(H*0.38)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (30, 80, 180), 2, cv2.LINE_AA)
    cv2.putText(frame, "Ket noi ESP32-CAM qua MQTT de chuyen sang REAL mode",
                (int(W*0.16), int(H*0.44)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 60, 120), 1, cv2.LINE_AA)

    return frame


# ════════════════════════════════════════════════════════════════════════════
# YOLO DETECTION
# ════════════════════════════════════════════════════════════════════════════

def _run_yolo(frame: np.ndarray) -> list:
    if _vehicle_model is not None:
        try:
            results = _vehicle_model(frame, verbose=False, conf=CONF_THRESHOLD)
            detections = []
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id   = int(box.cls[0])
                    conf     = float(box.conf[0])
                    xyxy     = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                    cls_name = _vehicle_model.names.get(cls_id, f"cls_{cls_id}")
                    detections.append((cls_id, cls_name, conf, x1, y1, x2, y2))
            with _perf_lock:
                _perf["detection_frames"] += 1
            return detections
        except Exception as e:
            log.debug("YOLO error: %s", e)
            return []
    else:
        return _demo_detections(frame)


def _demo_detections(frame: np.ndarray) -> list:
    if not hasattr(_demo_detections, "_pos"):
        _demo_detections._pos = 0
    h, w = frame.shape[:2]
    _demo_detections._pos = (_demo_detections._pos + 3) % (w - 80)
    x = _demo_detections._pos
    y = int(h * 0.70)
    return [(3, "motorcycle", 0.82, x, y-30, x+60, y+30)]


# ════════════════════════════════════════════════════════════════════════════
# OCR
# ════════════════════════════════════════════════════════════════════════════

_VN_PLATE_PATTERNS = [
    re.compile(r'\b(\d{2}[A-Z]\d?[-\s]?\d{4,5})\b', re.IGNORECASE),
    re.compile(r'\b(\d{2}[A-Z]{1,2}[-\s]?\d{4,5})\b', re.IGNORECASE),
]
_INTL_PLATE_PATTERNS = [
    re.compile(r'\b([A-Z]{1,3}[\s\-]?\d{3,4}[\s\-]?[A-Z]{0,2})\b', re.IGNORECASE),
    re.compile(r'\b([A-Z0-9]{5,8})\b'),
]


def _run_ocr(crop: np.ndarray) -> str:
    if _ocr_reader is None or crop is None or crop.size == 0:
        return ""
    try:
        h, w = crop.shape[:2]
        if w < 60 or h < 20:
            scale = max(60/w, 20/h)
            crop  = cv2.resize(crop, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)

        gray    = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.bilateralFilter(gray, 9, 75, 75)
        thresh  = cv2.adaptiveThreshold(blurred, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        proc    = cv2.cvtColor(cv2.bitwise_not(thresh), cv2.COLOR_GRAY2BGR)

        results  = _ocr_reader.readtext(proc,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. ",
                    detail=1, paragraph=False)
        if not results:
            with _perf_lock: _perf["ocr_fail"] += 1
            return ""

        all_text = " ".join(r[1].strip().upper() for r in results if r[2] > 0.3)
        all_text = all_text.replace("O", "0").replace("I", "1").replace("l", "1")

        for pat in _VN_PLATE_PATTERNS:
            m = pat.search(all_text)
            if m:
                plate = _normalize_vn_plate(m.group(1))
                if len(plate) >= OCR_MIN_CHARS:
                    with _perf_lock: _perf["ocr_success"] += 1
                    return plate

        for pat in _INTL_PLATE_PATTERNS:
            m = pat.search(all_text)
            if m:
                plate = m.group(1).strip().upper()
                if len(plate) >= OCR_MIN_CHARS:
                    with _perf_lock: _perf["ocr_success"] += 1
                    return plate

        with _perf_lock: _perf["ocr_fail"] += 1
        return ""
    except Exception as e:
        log.debug("OCR error: %s", e)
        with _perf_lock: _perf["ocr_fail"] += 1
        return ""


def _normalize_vn_plate(raw: str) -> str:
    p = raw.upper().replace(" ", "").replace(".", "").replace("-", "")
    m = re.match(r'^(\d{2}[A-Z]{1,2}\d?)(\d{4,5})$', p)
    return f"{m.group(1)}-{m.group(2)}" if m else raw.upper()


# ════════════════════════════════════════════════════════════════════════════
# MAIN DETECTION LOOP
# ════════════════════════════════════════════════════════════════════════════

def _detection_loop():
    """
    Camera Live detection loop.
    
    - Chờ model load xong
    - Mỗi ~30ms: lấy frame (ESP32 hoặc demo) → YOLO → push lên /video_feed
    - Đèn GREEN → skip detection, chỉ push frame
    - Đèn RED/YELLOW → detect → check ROI → OCR → process_violation
    
    KHÔNG mở VideoCapture ở đây.
    """
    log.info("⏳ Detection loop: waiting for models (timeout=120s)...")
    _models_ready.wait(timeout=120)
    if not _models_ready.is_set():
        log.error("❌ Models not ready after 120s — detection loop aborted")
        return

    log.info("🎯 Camera Live detection loop started (ESP32-CAM / Demo frames only)")

    fps_ts      = time.time()
    fps_count   = 0
    last_cap_ts = 0.0

    while not _stop_event.is_set():
        try:
            current_light = _AppRef.get_light()

            # GREEN: push empty context, skip detection
            if current_light == "GREEN":
                frame, src = _get_frame()
                # Vẫn push frame để Camera Live stream không đứng hình
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    _AppRef.push_frame(buf.tobytes())
                _AppRef.update_context(0, 0.0)
                time.sleep(0.2)
                continue

            # Get frame (ESP32 or demo — KHÔNG webcam)
            frame, src = _get_frame()

            # FPS tracking
            fps_count += 1
            now = time.time()
            elapsed = now - fps_ts
            if elapsed >= 3.0:
                fps = fps_count / elapsed
                with _perf_lock:
                    _perf["detection_fps"] = fps
                fps_ts = now; fps_count = 0
            else:
                with _perf_lock:
                    fps = _perf["detection_fps"]

            # YOLO
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
                vehicles_in_frame += 1

                box_color = (20, 20, 220) if current_light == "RED" else (0, 180, 220)
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                label = f"{cls_name} {conf*100:.0f}%"
                cv2.putText(frame, label, (x1+2, max(y1-6, 16)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, box_color, 1, cv2.LINE_AA)

                if current_light == "RED":
                    cx, cy = (x1+x2)//2, (y1+y2)//2
                    if roi_x1 <= cx <= roi_x2 and roi_y1 <= cy <= roi_y2:
                        cv2.rectangle(frame, (x1-3, y1-3), (x2+3, y2+3), (0, 0, 255), 3)
                        violations_detected.append({
                            "cls_id": cls_id, "cls_name": cls_name, "conf": conf,
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        })

            # ROI line
            roi_color = (50, 50, 220) if current_light == "RED" else (50, 200, 220)
            cv2.line(frame, (roi_x1, roi_y1), (roi_x2, roi_y1), roi_color, 2)
            cv2.putText(frame, "VACH DUNG - ROI",
                        (roi_x1+10, roi_y1-6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, roi_color, 1, cv2.LINE_AA)

            # Source badge
            badge = "ESP32-CAM ●" if src == "ESP32" else "DEMO ●"
            badge_color = (0, 200, 80) if src == "ESP32" else (0, 100, 200)
            cv2.putText(frame, badge, (roi_x1+10, roi_y1+18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, badge_color, 1)

            # Push annotated frame → /video_feed (Camera Live)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if ok:
                _AppRef.push_frame(buf.tobytes())

            # Capture throttle
            if (now - last_cap_ts) < CAPTURE_INTERVAL:
                _AppRef.update_context(vehicles_in_frame, fps)
                time.sleep(0.02)
                continue

            # Process violations (RED only)
            if current_light == "RED" and violations_detected:
                last_cap_ts = now
                for viol in violations_detected:
                    _handle_violation(frame, viol, vehicles_in_frame)

            _AppRef.update_context(vehicles_in_frame, fps,
                                   capture_interval=CAPTURE_INTERVAL,
                                   roi="STOP_LINE",
                                   target_objects=["MOTORBIKE", "CAR"],
                                   weather="SUN", distance=5.0)

            time.sleep(0.030)

        except Exception as e:
            log.error("Detection loop error: %s", e, exc_info=True)
            time.sleep(0.5)

    log.info("🛑 Detection loop stopped | frames=%d violations=%d",
             _perf["total_frames"], _perf["violations_found"])


# ════════════════════════════════════════════════════════════════════════════
# VIOLATION HANDLER
# ════════════════════════════════════════════════════════════════════════════

def _handle_violation(frame: np.ndarray, viol: dict, vehicles_in_frame: int):
    x1, y1, x2, y2 = viol["x1"], viol["y1"], viol["x2"], viol["y2"]
    h, w = frame.shape[:2]
    pad  = 15
    crop = frame[max(0,y1-pad):min(h,y2+pad), max(0,x1-pad):min(w,x2+pad)]
    plate = _run_ocr(crop)

    if plate:
        now = time.time()
        with _plate_lock:
            if now - _plate_seen.get(plate, 0) < PLATE_THROTTLE_SEC:
                return
            _plate_seen[plate] = now

    ok, buf  = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    image_b64 = base64.b64encode(buf.tobytes()).decode() if ok else ""

    vtype_map = {"car": "CAR", "motorcycle": "MOTORBIKE", "bus": "BUS", "truck": "TRUCK"}
    payload = {
        "ts":             int(time.time()),
        "plate":          plate or "UNKNOWN",
        "type":           vtype_map.get(viol["cls_name"], "UNKNOWN"),
        "speed_kmh":      0.0,
        "confidence":     round(viol["conf"], 4),
        "image_b64":      image_b64,
        "cam_id":         "ESP32-CAM" if _esp32_ever_connected.is_set() else "AI-DEMO",
        "roi":            "STOP_LINE",
        "vehicles_frame": vehicles_in_frame,
    }

    log.warning("🚨 VIOLATION: plate=%-12s type=%-10s conf=%.2f",
                payload["plate"], payload["type"], payload["confidence"])

    with _perf_lock:
        _perf["violations_found"] += 1

    _AppRef.process_violation(payload)

    if _ai_mqtt and _ai_mqtt.is_connected():
        try:
            import json as _json
            _ai_mqtt.publish(TOPIC_VIOLATION,
                             _json.dumps({k: v for k, v in payload.items() if k != "image_b64"}), qos=1)
        except Exception as e:
            log.debug("MQTT violation publish error: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ════════════════════════════════════════════════════════════════════════════

__all__ = ["start_ai", "sync_light_state", "get_esp32_status"]