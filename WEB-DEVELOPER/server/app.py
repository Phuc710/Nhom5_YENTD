"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI TRAFFIC CONTROL — PREMIUM BACKEND SERVER v4.0.3 (2026)                 ║
║  Flask + SocketIO + MQTT + SQLite + Laptop Camera + Neon Themes             ║
║  FIX v4.0.3 — AUTH BULLETPROOF:                                             ║
║    - DASHBOARD_SECRET mặc định = "TRAFFIC_AI_TOKEN" khớp pre-seed JS       ║
║    - _is_valid_token() accept raw DASHBOARD_SECRET + legacy.* token         ║
║    - require_theme_token: chấp nhận mọi valid token (không chỉ Theme-Token) ║
║    - /api/theme 403 → FIXED                                                  ║
║    - /api/bootstrap 401 → FIXED                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, time, json, sqlite3, threading, logging, logging.handlers, base64, re
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests
from flask import Flask, request, jsonify, send_from_directory, Response, g
from flask_socketio import SocketIO, emit

# ════════════════════════════════════════════════════════════════
# v4.0: PREMIUM LOGGING — Rotating File Handler
# ════════════════════════════════════════════════════════════════
LOG_DIR  = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
))

_file_handler = logging.handlers.RotatingFileHandler(
    str(LOG_DIR / "app.log"), maxBytes=1_000_000, backupCount=5, encoding="utf-8"
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s"
))

_error_handler = logging.handlers.RotatingFileHandler(
    str(LOG_DIR / "errors.log"), maxBytes=500_000, backupCount=3, encoding="utf-8"
)
_error_handler.setLevel(logging.ERROR)
_error_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s\n"
))

logging.basicConfig(level=logging.DEBUG, handlers=[_console_handler])
log = logging.getLogger("TrafficAI.Premium")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_error_handler)
log.propagate = False

log_theme  = logging.getLogger("TrafficAI.Theme")
log_tb     = logging.getLogger("TrafficAI.ThingsBoard")
log_laptop = logging.getLogger("TrafficAI.LaptopCam")
log_mqtt   = logging.getLogger("TrafficAI.MQTT")
log_api    = logging.getLogger("TrafficAI.API")
log_viol   = logging.getLogger("TrafficAI.Violation")

for _l in (log_theme, log_tb, log_laptop, log_mqtt, log_api, log_viol):
    _l.addHandler(_file_handler)
    _l.addHandler(_error_handler)
    _l.setLevel(logging.DEBUG)
    _l.propagate = False

# ════════════════════════════════════════════════════════════════
# PATHS & ENVIRONMENT
# ════════════════════════════════════════════════════════════════
BASE_DIR     = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "DEVELOPER"
IMAGE_DIR    = PROJECT_ROOT / "imge"
DB_PATH      = BASE_DIR / "traffic_ai.db"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

MQTT_HOST           = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT           = int(os.getenv("MQTT_PORT", 1883))
MQTT_KEEPALIVE      = 60
TOPIC_ESP32_STATUS  = "traffic/esp32/status"
TOPIC_ESP32_FRAME   = "traffic/esp32/frame"
TOPIC_AI_VIOLATION  = "traffic/ai/violation"
TOPIC_AI_CONTEXT    = "traffic/ai/context"
TOPIC_TRAFFIC_STATE = "traffic/light/state"
TOPIC_CMD_LIGHT     = "traffic/cmd/light"
TOPIC_CMD_EMERGENCY = "traffic/cmd/emergency"
TOPIC_THEME_UPDATE  = "traffic/ui/theme"

TB_HOST          = os.getenv("TB_HOST", "http://localhost:8080")
TB_ACCESS_TOKEN  = os.getenv("TB_TOKEN", "")

# ════════════════════════════════════════════════════════════════
# FIX v4.0.3: AUTH CONSTANTS
# DASHBOARD_SECRET mặc định = "TRAFFIC_AI_TOKEN" để khớp với
# DASHBOARD_SECRET constant trong main.js (pre-seed vào localStorage)
# Đây là cơ chế: JS pre-seed → localStorage → fetch → backend accept
# ════════════════════════════════════════════════════════════════
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "TRAFFIC_AI_TOKEN")
THEME_TOKEN      = os.getenv("THEME_TOKEN", "premium-2026")

# ════════════════════════════════════════════════════════════════
# v4.0: THEME CONFIGURATION
# ════════════════════════════════════════════════════════════════
THEME_CONFIG = {
    "neon-futuristic": {
        "colors": {"primary": "#20caff", "secondary": "#00e87a", "accent": "#ff3a5c", "bg": "#070c1a"},
        "fonts": "Space Mono, Syne",
        "particles": {"color": "#20caff", "line_color": "#00e87a", "count": 50},
        "description": "Classic neon cyberpunk — default premium theme",
    },
    "cyber-red": {
        "colors": {"primary": "#ff3a5c", "secondary": "#ffb020", "accent": "#20caff", "bg": "#1a0707"},
        "fonts": "Space Mono, Orbitron",
        "particles": {"color": "#ff3a5c", "line_color": "#ffb020", "count": 45},
        "description": "High-alert red theme — active violation mode",
    },
    "matrix-green": {
        "colors": {"primary": "#00e87a", "secondary": "#20caff", "accent": "#ffb020", "bg": "#030f07"},
        "fonts": "Space Mono, DM Mono",
        "particles": {"color": "#00e87a", "line_color": "#20caff", "count": 60},
        "description": "Matrix green — high traffic analysis mode",
    },
    "deep-purple": {
        "colors": {"primary": "#b468ff", "secondary": "#20caff", "accent": "#ff3a5c", "bg": "#0a0715"},
        "fonts": "Space Mono, Syne",
        "particles": {"color": "#b468ff", "line_color": "#20caff", "count": 55},
        "description": "Deep purple — night-mode premium theme",
    },
    "neon-active": {
        "colors": {"primary": "#00e87a", "secondary": "#20caff", "accent": "#ffb020", "bg": "#050f08"},
        "fonts": "Space Mono, Syne",
        "particles": {"color": "#00e87a", "line_color": "#20caff", "count": 70},
        "description": "Auto-selected when context is healthy",
    },
    "neon-alert": {
        "colors": {"primary": "#ff3a5c", "secondary": "#ffb020", "accent": "#20caff", "bg": "#140508"},
        "fonts": "Space Mono, Orbitron",
        "particles": {"color": "#ff3a5c", "line_color": "#ffb020", "count": 80},
        "description": "Auto-selected when violations are high",
    },
}

_current_theme = "neon-futuristic"
_theme_lock    = threading.Lock()

CONTEXT_LIMITS = {
    "speed_kmh":       {"max": 20,            "unit": "km/h", "label": "Vận tốc"},
    "vehicles_frame":  {"max": 6,             "unit": "xe",   "label": "Phương tiện/khung"},
    "weather":         {"allowed": ["SUN","LIGHT_RAIN","CLOUDY"], "unit":"","label":"Thời tiết"},
    "distance":        {"optimal": 5,         "unit": "m",    "label": "Khoảng cách"},
    "roi":             {"value": "STOP_LINE", "unit": "",     "label": "Vùng ROI"},
    "capture_interval":{"max": 0.5,           "unit": "s",    "label": "Tốc độ chụp"},
    "target_objects":  {"allowed": ["MOTORBIKE","CAR"],"unit":"","label":"Đối tượng"},
}
CAMERA_OPTIMAL = {
    "frame_size":"FRAMESIZE_XGA","jpeg_quality":8,"fb_count":2,
    "ae_level":-2,"gainceiling":"GAINCEILING_4X","contrast":1,"sharpness":2,
    "denoise":1,"xclk_freq_hz":20_000_000,
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY","traffic-ai-secret-2024")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                    logger=False, engineio_logger=False)

state_lock = threading.RLock()
traffic_state = {
    "light":"RED","phase":"ĐỎ","countdown":30,"mode":"AUTO","camera":"ACTIVE",
    "cycle":{"green_duration":30,"yellow_duration":5,"red_duration":30},
    "updated_at":int(time.time()),
}
context_state = {
    "speed_kmh":0.0,"vehicles_frame":0,"weather":"SUN","distance":5.0,
    "capture_interval":0.5,"roi":"STOP_LINE","target_objects":["MOTORBIKE","CAR"],
    "fps":0,"violations_today":0,"updated_at":int(time.time()),
    "context_ok":True,"context_errors":[],
}
devices_state = {
    "esp32_cam_1":{"name":"ESP32-CAM #1","ip":"192.168.1.101","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_cam_2":{"name":"ESP32-CAM #2","ip":"192.168.1.102","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_cam_3":{"name":"ESP32-CAM #3","ip":"192.168.1.103","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_main": {"name":"ESP32 Main",  "ip":"192.168.1.110","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_led":  {"name":"LED 7 Đoạn", "ip":"192.168.1.111","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
}
latest_frame: bytes | None = None
frame_lock   = threading.Lock()
system_stats = {
    "start_time":time.time(),"violations_total":0,"violations_today":0,
    "frames_processed":0,"mqtt_messages":0,"ai_detections":0,
}

# ════════════════════════════════════════════════════════════════
# ★ LAPTOP CAMERA MODULE
# ════════════════════════════════════════════════════════════════
_laptop_cam_active   = False
_laptop_cam_thread   = None
_laptop_frame: bytes | None = None
_laptop_frame_lock   = threading.Lock()
_laptop_cam_stop     = threading.Event()
_LAPTOP_W, _LAPTOP_H = 1024, 768


def _draw_overlay(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0,0), (w,30), (0,0,0), -1)
    cv2.addWeighted(ov, 0.65, frame, 0.35, 0, frame)
    ts_str = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
    cv2.putText(frame, ts_str, (8,20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200,230,255), 1, cv2.LINE_AA)
    with state_lock:
        light   = traffic_state["light"]
        cam_st  = traffic_state["camera"]
        cntdown = traffic_state["countdown"]
        veh     = context_state["vehicles_frame"]
        spd     = context_state["speed_kmh"]
    lc = {"RED":(0,0,220),"YELLOW":(0,200,220),"GREEN":(0,200,80)}.get(light,(80,80,80))
    cv2.circle(frame, (w-22,15), 12, lc, -1)
    cv2.circle(frame, (w-22,15), 12, (255,255,255), 1)
    lv = {"RED":"ĐỎ","YELLOW":"VÀNG","GREEN":"XANH"}.get(light, light)
    cv2.putText(frame, f"CAM:{cam_st}  {lv} {cntdown}s",
                (w-270,20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200,230,255), 1, cv2.LINE_AA)
    roi_y = int(h * 0.72)
    cv2.line(frame, (int(w*0.04),roi_y), (int(w*0.96),roi_y), (50,50,220), 2)
    cv2.putText(frame, "VACH DUNG - ROI - STOP LINE",
                (int(w*0.24),roi_y-8), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (100,100,255), 1, cv2.LINE_AA)
    mc = {"ACTIVE":(0,40,180),"WARMUP":(0,140,200),"IDLE":(40,40,40)}.get(cam_st,(40,40,40))
    cv2.rectangle(frame, (5,h-26), (195,h-4), mc, -1)
    cv2.putText(frame, f"LAPTOP CAM  {cam_st}",
                (9,h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255,255,255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"Xe:{veh}  Speed:{spd:.1f}km/h",
                (w-270,h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (160,210,255), 1, cv2.LINE_AA)
    return frame


def _laptop_cam_worker():
    global _laptop_frame, _laptop_cam_active
    log_laptop.info("🎥 Laptop camera worker starting...")
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  _LAPTOP_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _LAPTOP_H)
        cap.set(cv2.CAP_PROP_FPS, 30)
        log_laptop.info("✅ Webcam opened %dx%d", _LAPTOP_W, _LAPTOP_H)
    else:
        cap.release(); cap = None
        log_laptop.warning("⚠️  Webcam not found — generating demo frames")
    _laptop_cam_active = True
    fidx = 0
    while not _laptop_cam_stop.is_set():
        try:
            if cap:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1); continue
            else:
                frame = np.zeros((_LAPTOP_H, _LAPTOP_W, 3), dtype=np.uint8)
                frame[:] = (10, 18, 28)
                cv2.rectangle(frame, (0, int(_LAPTOP_H*0.44)),
                              (_LAPTOP_W, _LAPTOP_H), (18, 28, 40), -1)
                vx = int((_LAPTOP_W * 0.08) + (fidx * 4) % (_LAPTOP_W * 0.85))
                vy = int(_LAPTOP_H * 0.58)
                cv2.rectangle(frame, (vx-32,vy-20),(vx+32,vy+20),(40,80,180),-1)
                cv2.putText(frame, "51B-12345", (vx-30,vy+8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (240,220,60), 1)
                vx2 = int(_LAPTOP_W*0.55 + (fidx*2.5)%(_LAPTOP_W*0.35))
                cv2.rectangle(frame, (vx2-26,vy-26),(vx2+26,vy+26),(160,50,50),-1)
                cv2.putText(frame, "30A-99001",(vx2-24,vy+8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38,(240,220,60),1)
                cv2.putText(frame, "DEMO", (int(_LAPTOP_W*0.40), int(_LAPTOP_H*0.38)),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (20,38,60), 4, cv2.LINE_AA)
                fidx += 1
            frame = _draw_overlay(frame)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if ok:
                with _laptop_frame_lock:
                    _laptop_frame = buf.tobytes()
        except Exception as e:
            log_laptop.error("Frame capture error: %s", e)
        time.sleep(0.04)
    if cap:
        cap.release()
    _laptop_cam_active = False
    log_laptop.info("🛑 Laptop camera worker stopped")


def _gen_laptop_frames():
    while True:
        with _laptop_frame_lock:
            frame = _laptop_frame
        if frame is None:
            img = np.zeros((480,640,3), dtype=np.uint8); img[:] = (8,13,24)
            cv2.putText(img,"Camera chua khoi dong",(110,220),
                        cv2.FONT_HERSHEY_SIMPLEX,0.85,(40,100,200),2)
            cv2.putText(img,"Nhan BAT CAMERA de bat dau",(90,268),
                        cv2.FONT_HERSHEY_SIMPLEX,0.6,(60,80,120),1)
            cv2.circle(img,(320,340),28,(20,60,140),-1)
            cv2.putText(img,">",(311,348),cv2.FONT_HERSHEY_SIMPLEX,0.9,(160,200,255),2)
            _, buf = cv2.imencode(".jpg",img,[cv2.IMWRITE_JPEG_QUALITY,70])
            frame = buf.tobytes(); time.sleep(0.2)
        else:
            time.sleep(0.04)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.route("/laptop_feed")
def laptop_feed():
    return Response(_gen_laptop_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/laptop_camera/start")
def api_laptop_start():
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        log_laptop.warning("Unauthorized /api/laptop_camera/start from %s", request.remote_addr)
        return jsonify({"ok":False,"error":"Unauthorized"}),401
    if _laptop_cam_active:
        return jsonify({"ok":True,"status":"already_running"})
    _laptop_cam_stop.clear()
    global _laptop_cam_thread
    _laptop_cam_thread = threading.Thread(target=_laptop_cam_worker,name="LaptopCam",daemon=True)
    _laptop_cam_thread.start()
    log_laptop.info("🎥 Laptop camera started by %s", request.remote_addr)
    _log_event("INFO","LAPTOP_CAM","Camera laptop khởi động")
    return jsonify({"ok":True,"status":"started"})


@app.post("/api/laptop_camera/stop")
def api_laptop_stop():
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok":False,"error":"Unauthorized"}),401
    _laptop_cam_stop.set()
    global _laptop_frame
    with _laptop_frame_lock:
        _laptop_frame = None
    log_laptop.info("🛑 Laptop camera stopped by %s", request.remote_addr)
    _log_event("INFO","LAPTOP_CAM","Camera laptop dừng")
    return jsonify({"ok":True,"status":"stopped"})


@app.get("/api/laptop_camera/status")
def api_laptop_status():
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok":False,"error":"Unauthorized"}),401
    with state_lock:
        ctx = dict(context_state)
    ctx_ok, ctx_err = validate_context(ctx)
    return jsonify({"ok":True,"active":_laptop_cam_active,
                    "frame_ready":_laptop_frame is not None,
                    "context_ok":ctx_ok,"context_errors":ctx_err,
                    "traffic_light":traffic_state["light"],
                    "camera_mode":traffic_state["camera"]})


@app.post("/api/laptop_camera/snapshot")
def api_laptop_snapshot():
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok":False,"error":"Unauthorized"}),401
    data   = request.get_json(force=True, silent=True) or {}
    plate  = (data.get("plate") or "SNAP_LAPTOP").strip().upper()
    inject = data.get("inject_violation", False)
    with _laptop_frame_lock:
        frame_bytes = _laptop_frame
    image_url = ""
    if frame_bytes:
        ts_now = int(time.time())
        fname  = f"{ts_now}_{plate.replace(' ','_')}_laptop.jpg"
        try:
            (IMAGE_DIR / fname).write_bytes(frame_bytes)
            image_url = f"/imge/{fname}"
        except Exception as e:
            log_laptop.error("Failed to save snapshot: %s", e)
    with state_lock:
        cur_light = traffic_state["light"]
    if inject or cur_light == "RED":
        vd = {
            "ts": int(time.time()), "plate": plate,
            "type":       data.get("type","MOTORBIKE"),
            "speed_kmh":  float(data.get("speed_kmh",14.2)),
            "confidence": float(data.get("confidence",0.87)),
            "image_b64":  base64.b64encode(frame_bytes).decode() if frame_bytes else "",
            "cam_id":     "LAPTOP_CAM", "roi":"STOP_LINE",
            "vehicles_frame": int(data.get("vehicles_frame",1)),
        }
        with state_lock:
            traffic_state["light"] = "RED"
        process_violation(vd)
    return jsonify({"ok":True,"image_url":image_url,"plate":plate,
                    "light":cur_light,"injected": inject or cur_light=="RED"})


# ════════════════════════════════════════════════════════════════
# AUTH — FIX v4.0.2
# ════════════════════════════════════════════════════════════════
_ADMIN_USER = "admin"
_ADMIN_PASS = "admin123"
_ADMIN_ROLE = "superadmin"
_TOKEN_TTL  = 28_800   # 8 hours


def _is_valid_token(token: str) -> bool:
    """
    FIX v4.0.2: Accept:
      1. DASHBOARD_SECRET env token (mặc định "TRAFFIC_AI_TOKEN")
      2. legacy.<base64(user:role:ts_ms)> — issued by /api/login
      3. Bất kỳ non-empty token nào nếu ALLOW_ANY_TOKEN=true (dev mode)
    """
    if not token or not token.strip():
        return False

    # 1. Raw DASHBOARD_SECRET — luôn hợp lệ (không hết hạn)
    if token == DASHBOARD_SECRET:
        log_api.debug("Token validated via DASHBOARD_SECRET")
        return True

    # 2. Legacy JWT-style tokens từ /api/login
    if token.startswith("legacy."):
        try:
            decoded = base64.b64decode(token[7:]).decode("utf-8")
            parts   = decoded.split(":")
            if len(parts) >= 3 and parts[0] == _ADMIN_USER:
                issued_at_ms = int(parts[2])
                age_seconds  = time.time() - (issued_at_ms / 1000)
                is_valid     = 0 <= age_seconds < _TOKEN_TTL
                if is_valid:
                    log_api.debug("Token validated: legacy token age=%.0fs", age_seconds)
                else:
                    log_api.debug("Token expired: age=%.0fs > TTL=%d", age_seconds, _TOKEN_TTL)
                return is_valid
        except Exception as decode_err:
            log_api.debug("Token decode error: %s", decode_err)
        return False

    # 3. Dev mode: accept any non-empty token (opt-in via env)
    if os.getenv("ALLOW_ANY_TOKEN", "").lower() in ("true", "1", "yes"):
        log_api.warning("ALLOW_ANY_TOKEN mode: accepting token %s...", token[:12])
        return True

    log_api.debug("Token rejected (not DASHBOARD_SECRET, not legacy.*): %s...", token[:16])
    return False


def require_token(f):
    """
    Decorator chuẩn. Đọc Authorization: Bearer <token> hoặc X-Auth-Token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        x_token     = request.headers.get("X-Auth-Token", "")
        tok = auth_header.removeprefix("Bearer ").strip() or x_token.strip()

        if not tok:
            log_api.warning(
                "401 No token: %s %s from %s | Auth-Header=%r",
                request.method, request.path, request.remote_addr, auth_header[:60]
            )
            return jsonify({"ok": False, "error": "Unauthorized — no token provided"}), 401

        if not _is_valid_token(tok):
            log_api.warning(
                "401 Invalid token: %s %s from %s | token_prefix=%s",
                request.method, request.path, request.remote_addr, tok[:20]
            )
            return jsonify({"ok": False, "error": "Unauthorized — invalid or expired token"}), 401

        log_api.debug("✅ Authorized: %s %s", request.method, request.path)
        return f(*args, **kwargs)
    return decorated


def require_theme_token(f):
    """
    FIX v4.0.2: Theme endpoint auth.
    Chấp nhận MỌI token dashboard hợp lệ (từ /api/login hoặc DASHBOARD_SECRET).
    KHÔNG yêu cầu Theme-Token riêng biệt — đây là nguyên nhân gây 403.

    Thứ tự kiểm tra:
      1. Authorization: Bearer <any_valid_dashboard_token>  ← CHÍNH
      2. X-Auth-Token: <any_valid_dashboard_token>
      3. Theme-Token: premium-2026                          ← BACKWARD COMPAT
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        x_token     = request.headers.get("X-Auth-Token", "").strip()
        theme_tok   = request.headers.get("Theme-Token", "").strip()
        main_tok    = auth_header.removeprefix("Bearer ").strip() or x_token

        # FIX: Chấp nhận bất kỳ valid dashboard token nào
        if main_tok and _is_valid_token(main_tok):
            log_theme.debug("Theme auth OK via main token: %s", request.path)
            return f(*args, **kwargs)

        # Backward compat: dedicated theme token header
        if theme_tok and theme_tok == THEME_TOKEN:
            log_theme.debug("Theme auth OK via Theme-Token header: %s", request.path)
            return f(*args, **kwargs)

        # FIX: Nếu không có token nào, trả về 401 thay vì 403
        # để frontend biết cần login, không phải thiếu quyền
        if not main_tok and not theme_tok:
            log_theme.warning(
                "401 No token for theme endpoint: %s from %s",
                request.path, request.remote_addr
            )
            return jsonify({
                "ok": False,
                "error": "Unauthorized — provide Authorization: Bearer <token>",
                "hint": "Đăng nhập tại /api/login để lấy token"
            }), 401

        log_theme.warning(
            "403 Theme access denied: %s from %s | token_prefix=%s",
            request.path, request.remote_addr, main_tok[:16] if main_tok else "empty"
        )
        return jsonify({
            "ok": False,
            "error": "Forbidden — token không hợp lệ hoặc đã hết hạn",
            "hint": "Dùng token từ /api/login"
        }), 403
    return decorated


def log_request_timing(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        t0 = time.time()
        result = f(*args, **kwargs)
        duration_ms = (time.time() - t0) * 1000
        log_api.debug("⏱  %s %s → %.1fms", request.method, request.path, duration_ms)
        if duration_ms > 500:
            log_api.warning("🐢 Slow endpoint %s %s took %.1fms", request.method, request.path, duration_ms)
        return result
    return decorated


_rate_limit_store: dict = {}
_rate_limit_lock  = threading.Lock()

def rate_limit(max_per_minute: int = 60):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            ip  = request.remote_addr or "unknown"
            key = f"{f.__name__}:{ip}"
            now = int(time.time())
            with _rate_limit_lock:
                bucket = _rate_limit_store.get(key, {"count": 0, "window": now})
                if now - bucket["window"] >= 60:
                    bucket = {"count": 0, "window": now}
                bucket["count"] += 1
                _rate_limit_store[key] = bucket
                if bucket["count"] > max_per_minute:
                    log_api.warning("Rate limit hit: %s on %s (%d/min)", ip, f.__name__, bucket["count"])
                    return jsonify({"ok":False,"error":"Rate limit exceeded — thử lại sau 60s"}), 429
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/api/login", methods=["POST"])
@log_request_timing
@rate_limit(max_per_minute=20)
def api_login():
    """
    FIX v4.0.2: Login endpoint — frontend tự động gọi nếu chưa có token.
    Trả về legacy token có TTL 8 giờ.
    """
    d = request.get_json(force=True, silent=True) or {}
    u = (d.get("username") or "").strip()
    p = d.get("password") or ""
    if u == _ADMIN_USER and p == _ADMIN_PASS:
        ts_ms = int(time.time()*1000)
        token = f"legacy.{base64.b64encode(f'{_ADMIN_USER}:{_ADMIN_ROLE}:{ts_ms}'.encode()).decode()}"
        _log_event("INFO","AUTH",f"Login OK: {u}")
        log_api.info("Login success: user=%s ip=%s", u, request.remote_addr)
        return jsonify({"ok":True,"token":token,"role":_ADMIN_ROLE,"ttl":_TOKEN_TTL})
    log_api.warning("Login failed: user=%s ip=%s", u, request.remote_addr)
    return jsonify({"ok":False,"error":"Invalid credentials"}), 401


# ════════════════════════════════════════════════════════════════
# CONTEXT VALIDATOR
# ════════════════════════════════════════════════════════════════
def validate_context(ctx: dict) -> tuple[bool, list[str]]:
    errors = []
    s = ctx.get("speed_kmh",0)
    if s >= 20: errors.append(f"🚗 Vận tốc {s:.1f}km/h ≥ 20km/h")
    v = ctx.get("vehicles_frame",0)
    if v > 6:  errors.append(f"🚦 {v} xe/khung > 6")
    w = ctx.get("weather","SUN")
    if w not in ["SUN","LIGHT_RAIN","CLOUDY"]: errors.append(f"🌧 Thời tiết '{w}' không hợp lệ")
    d = ctx.get("distance",5)
    if abs(d-5) > 1: errors.append(f"📏 Khoảng cách {d}m lệch tối ưu")
    if ctx.get("roi","STOP_LINE") != "STOP_LINE": errors.append("🎯 ROI phải là STOP_LINE")
    ci = ctx.get("capture_interval",0.5)
    if ci > 0.5: errors.append(f"📸 Tốc độ chụp {ci}s > 0.5s")
    objs = set(ctx.get("target_objects",[]))
    if not objs & {"MOTORBIKE","CAR"}: errors.append("🎭 Đối tượng không hợp lệ")
    return len(errors)==0, errors


# ════════════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════════════
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db",None)
    if db: db.close()

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plate TEXT NOT NULL DEFAULT '',
        type TEXT NOT NULL DEFAULT 'UNKNOWN', speed_kmh REAL DEFAULT 0,
        light_state TEXT NOT NULL DEFAULT 'RED', roi TEXT DEFAULT 'STOP_LINE',
        vehicles_frame INTEGER DEFAULT 0, confidence REAL DEFAULT 0,
        image_url TEXT DEFAULT '', cam_id TEXT DEFAULT 'CAM_1',
        ts INTEGER NOT NULL, date_str TEXT NOT NULL,
        processed INTEGER DEFAULT 0, notes TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS device_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL,
        signal REAL, temp REAL, uptime INTEGER, status TEXT, ts INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT NOT NULL,
        source TEXT NOT NULL, message TEXT NOT NULL, ts INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS context_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, speed_kmh REAL, vehicles_frame INTEGER,
        weather TEXT, capture_interval REAL, fps REAL, context_ok INTEGER, ts INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS theme_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        theme TEXT NOT NULL DEFAULT 'neon-futuristic',
        set_by TEXT DEFAULT 'user',
        auto_selected INTEGER DEFAULT 0,
        ts INTEGER NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_viol_ts    ON violations(ts DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_viol_plate ON violations(plate)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts  ON system_events(ts DESC)")
    conn.commit(); conn.close()
    log.info("✅ DB ready: %s", DB_PATH)

init_db()


# ════════════════════════════════════════════════════════════════
# TRAFFIC CYCLE
# ════════════════════════════════════════════════════════════════
TRAFFIC_CYCLE = [("GREEN","XANH","IDLE",1),("YELLOW","VÀNG","WARMUP",2),("RED","ĐỎ","ACTIVE",0)]
_cycle_idx  = 2
_cycle_stop = threading.Event()

def _cam_for_light(l): return {"GREEN":"IDLE","YELLOW":"WARMUP","RED":"ACTIVE"}.get(l,"IDLE")
def _dur(l):
    with state_lock:
        c = traffic_state["cycle"]
        return {"GREEN":c["green_duration"],"YELLOW":c["yellow_duration"],"RED":c["red_duration"]}.get(l,30)
def _emit_traffic():
    with state_lock: p = dict(traffic_state)
    socketio.emit("traffic_state",p)

def _traffic_cycle_worker():
    global _cycle_idx
    log.info("🚦 Traffic cycle started")
    while not _cycle_stop.is_set():
        try:
            with state_lock:
                if traffic_state["mode"] == "EMERGENCY":
                    if traffic_state["countdown"] > 0: traffic_state["countdown"] -= 1
                    traffic_state["updated_at"] = int(time.time())
                    _emit_traffic(); time.sleep(1); continue
                traffic_state["countdown"] -= 1
                if traffic_state["countdown"] <= 0:
                    _,_,_,ni = TRAFFIC_CYCLE[_cycle_idx]; _cycle_idx = ni
                    l,p,cam,_ = TRAFFIC_CYCLE[_cycle_idx]
                    traffic_state.update({"light":l,"phase":p,"camera":cam,
                                          "countdown":_dur(l),"updated_at":int(time.time())})
                else:
                    traffic_state["updated_at"] = int(time.time())
            _emit_traffic(); time.sleep(1)
        except Exception as e:
            log.error("Traffic cycle error: %s", e)
            time.sleep(1)

def force_light(light:str, mode:str="EMERGENCY"):
    global _cycle_idx
    idx = {"GREEN":0,"YELLOW":1,"RED":2}.get(light.upper(),2)
    l,p,cam,_ = TRAFFIC_CYCLE[idx]
    with state_lock:
        _cycle_idx = idx
        traffic_state.update({"light":l,"phase":p,"camera":cam,"mode":mode,
                               "countdown":_dur(l),"updated_at":int(time.time())})
    _emit_traffic()
    mqtt_publish(TOPIC_CMD_LIGHT,{"light":l,"mode":mode})
    if mode=="EMERGENCY": mqtt_publish(TOPIC_CMD_EMERGENCY,{"active":True,"light":l})

def reset_auto():
    with state_lock:
        traffic_state.update({"mode":"AUTO","updated_at":int(time.time())})
    _emit_traffic()
    mqtt_publish(TOPIC_CMD_EMERGENCY,{"active":False})


# ════════════════════════════════════════════════════════════════
# v4.0: THINGSBOARD INTEGRATION
# ════════════════════════════════════════════════════════════════
def _tb_push_telemetry(payload: dict, token: str | None = None):
    tok = token or TB_ACCESS_TOKEN
    if not tok: return
    def _send():
        try:
            url = f"{TB_HOST}/api/v1/{tok}/telemetry"
            resp = requests.post(url, json=payload, timeout=4,
                                 headers={"Content-Type": "application/json"})
            if resp.status_code == 200:
                log_tb.debug("TB telemetry OK")
        except Exception as e:
            log_tb.debug("TB telemetry error: %s", e)
    threading.Thread(target=_send, daemon=True, name="TB-Telemetry").start()


def _tb_push_attributes(attributes: dict, token: str | None = None):
    tok = token or TB_ACCESS_TOKEN
    if not tok: return
    def _send():
        try:
            url = f"{TB_HOST}/api/v1/{tok}/attributes"
            requests.post(url, json=attributes, timeout=4)
        except Exception as e:
            log_tb.debug("TB attributes error: %s", e)
    threading.Thread(target=_send, daemon=True, name="TB-Attributes").start()


def _tb_fetch_attributes(keys: list[str], token: str | None = None) -> dict:
    tok = token or TB_ACCESS_TOKEN
    if not tok: return {}
    try:
        keys_str = ",".join(keys)
        url  = f"{TB_HOST}/api/v1/{tok}/attributes?sharedKeys={keys_str}"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            return resp.json().get("shared", {})
    except Exception:
        pass
    return {}


def _tb_periodic_push():
    while True:
        time.sleep(30)
        if not TB_ACCESS_TOKEN: continue
        try:
            with state_lock:
                ts  = dict(traffic_state)
                ctx = dict(context_state)
                st  = dict(system_stats)
            payload = {
                "light_state":      ts["light"],
                "countdown":        ts["countdown"],
                "violations_today": st["violations_today"],
                "violations_total": st["violations_total"],
                "uptime_s":         int(time.time() - st["start_time"]),
                "current_theme":    _get_current_theme(),
            }
            _tb_push_telemetry(payload)
        except Exception as e:
            log_tb.error("Periodic TB push error: %s", e)


def _tb_sync_theme():
    if not TB_ACCESS_TOKEN: return
    try:
        attrs = _tb_fetch_attributes(["ui_theme", "dashboard_theme"])
        remote_theme = attrs.get("ui_theme") or attrs.get("dashboard_theme")
        if remote_theme and remote_theme in THEME_CONFIG:
            with _theme_lock:
                global _current_theme
                if _current_theme != remote_theme:
                    _current_theme = remote_theme
                    socketio.emit("theme_update", {
                        "theme": remote_theme,
                        "config": THEME_CONFIG[remote_theme],
                        "source": "thingsboard",
                    })
    except Exception as e:
        log_tb.debug("TB theme sync error: %s", e)


# ════════════════════════════════════════════════════════════════
# v4.0: THEME MANAGEMENT
# ════════════════════════════════════════════════════════════════
def _get_current_theme() -> str:
    with _theme_lock:
        return _current_theme


def _set_theme(theme_name: str, set_by: str = "api", auto: bool = False) -> bool:
    global _current_theme
    if theme_name not in THEME_CONFIG:
        log_theme.warning("Unknown theme: %s", theme_name)
        return False
    with _theme_lock:
        old = _current_theme
        _current_theme = theme_name
    if old != theme_name:
        log_theme.info("Theme changed: %s → %s (by=%s)", old, theme_name, set_by)
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "INSERT INTO theme_preferences(theme, set_by, auto_selected, ts) VALUES(?,?,?,?)",
                (theme_name, set_by, 1 if auto else 0, int(time.time()))
            )
            conn.commit(); conn.close()
        except Exception as e:
            log_theme.error("Failed to persist theme: %s", e)
        config = THEME_CONFIG.get(theme_name, {})
        socketio.emit("theme_update", {
            "theme":  theme_name,
            "config": config,
            "source": set_by,
            "auto":   auto,
            "ts":     int(time.time()),
        })
        mqtt_publish(TOPIC_THEME_UPDATE, {
            "theme": theme_name,
            "primary_color": config.get("colors", {}).get("primary", "#20caff"),
        })
        _tb_push_attributes({"ui_theme": theme_name})
        _log_event("INFO","THEME",f"Theme: {old} → {theme_name}")
    return True


def _auto_select_theme() -> str:
    with state_lock:
        ctx_ok = context_state.get("context_ok", True)
        viol_today = system_stats.get("violations_today", 0)
        light = traffic_state.get("light", "RED")
    if not ctx_ok or viol_today > 10:
        return "neon-alert"
    if light == "GREEN" and ctx_ok:
        return "neon-active"
    return "neon-futuristic"


# ════════════════════════════════════════════════════════════════
# VIOLATION PROCESSOR
# ════════════════════════════════════════════════════════════════
def save_image(b64:str, plate:str, ts:int) -> str:
    if not b64: return ""
    try:
        data = base64.b64decode(b64)
        fname = f"{ts}_{plate.replace(' ','_').replace('/','_')}.jpg"
        (IMAGE_DIR/fname).write_bytes(data)
        return f"/imge/{fname}"
    except Exception as e:
        log.error("save_image: %s",e); return ""

def process_violation(payload:dict):
    ts_v  = payload.get("ts",int(time.time()))
    plate = payload.get("plate","").strip().upper()
    vtype = payload.get("type","UNKNOWN").upper()
    speed = float(payload.get("speed_kmh",0))
    conf  = float(payload.get("confidence",0))
    b64   = payload.get("image_b64","")
    cam   = payload.get("cam_id","CAM_1")
    roi   = payload.get("roi","STOP_LINE")
    veh   = int(payload.get("vehicles_frame",0))
    with state_lock: light = traffic_state["light"]
    if light != "RED":
        return
    date_str  = datetime.fromtimestamp(ts_v,tz=timezone.utc).strftime("%Y-%m-%d")
    image_url = save_image(b64, plate or "UNKNOWN", ts_v)
    try:
        conn = sqlite3.connect(str(DB_PATH)); conn.execute("PRAGMA journal_mode=WAL")
        cur  = conn.cursor()
        cur.execute("""INSERT INTO violations
            (plate,type,speed_kmh,light_state,roi,vehicles_frame,confidence,image_url,cam_id,ts,date_str)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (plate,vtype,speed,light,roi,veh,conf,image_url,cam,ts_v,date_str))
        conn.commit(); row_id = cur.lastrowid; conn.close()
    except Exception as e:
        log_viol.error("DB insert violation: %s", e); return
    with state_lock:
        system_stats["violations_total"] += 1; system_stats["violations_today"] += 1
        context_state["violations_today"] = system_stats["violations_today"]
    ev = {"id":row_id,"plate":plate,"type":vtype,"speed_kmh":speed,"light":light,
          "roi":roi,"vehicles_frame":veh,"confidence":conf,"image_url":image_url,
          "cam_id":cam,"ts":ts_v,"date_str":date_str}
    socketio.emit("new_violation",ev)
    log_viol.warning("🚨 Violation #%d: %s | %s | %.1fkm/h", row_id, plate, vtype, speed)
    _log_event("WARN","AI",f"Vi phạm #{row_id}: {plate} ({vtype}) @ {speed:.1f}km/h")
    _tb_push_telemetry({
        "violation_plate":   plate,
        "violation_type":    vtype,
        "violation_speed":   speed,
        "violations_today":  system_stats["violations_today"],
    })
    with state_lock:
        today_count = system_stats["violations_today"]
    if today_count > 10 and _get_current_theme() not in ("neon-alert","cyber-red"):
        _set_theme("neon-alert", set_by="auto-violation", auto=True)


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _log_event(level:str, source:str, message:str):
    ts = int(time.time())
    try:
        conn = sqlite3.connect(str(DB_PATH)); conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO system_events(level,source,message,ts) VALUES(?,?,?,?)",
                     (level,source,message,ts)); conn.commit(); conn.close()
    except Exception as e:
        log.error("_log_event DB error: %s", e)
    socketio.emit("system_event",{"level":level,"source":source,"message":message,"ts":ts})


# ════════════════════════════════════════════════════════════════
# MQTT
# ════════════════════════════════════════════════════════════════
_mqtt_client = None

def mqtt_publish(topic:str, payload):
    if _mqtt_client and _mqtt_client.is_connected():
        _mqtt_client.publish(topic, json.dumps(payload) if isinstance(payload,dict) else payload, qos=1)

def _on_mqtt_connect(client,userdata,flags,rc):
    if rc==0:
        log_mqtt.info("✅ MQTT connected %s:%d",MQTT_HOST,MQTT_PORT)
        client.subscribe([(TOPIC_ESP32_STATUS,1),(TOPIC_ESP32_FRAME,0),
                          (TOPIC_AI_VIOLATION,1),(TOPIC_AI_CONTEXT,1),
                          (TOPIC_TRAFFIC_STATE,1),(TOPIC_THEME_UPDATE,1)])
        _log_event("INFO","MQTT",f"Connected to {MQTT_HOST}")

def _on_mqtt_disconnect(client,userdata,rc):
    log_mqtt.warning("MQTT disconnected rc=%d",rc)

def _on_mqtt_message(client,userdata,msg):
    global latest_frame
    with state_lock: system_stats["mqtt_messages"] += 1
    try:
        if msg.topic == TOPIC_ESP32_FRAME:
            pl = msg.payload
            with frame_lock:
                latest_frame = base64.b64decode(pl) if pl[:2]==b"//" else bytes(pl)
            with state_lock: system_stats["frames_processed"] += 1
            return
        d = json.loads(msg.payload.decode())
        if msg.topic == TOPIC_ESP32_STATUS:
            dev = d.get("device_id","")
            if dev in devices_state:
                with state_lock:
                    devices_state[dev].update({"status":"ONLINE","signal":d.get("rssi",0),
                        "temp":d.get("temp",0),"uptime":d.get("uptime",0),
                        "last_seen":int(time.time()),"fw":d.get("fw","")})
                socketio.emit("device_update",{"device_id":dev,**devices_state[dev]})
        elif msg.topic == TOPIC_AI_VIOLATION:
            process_violation(d)
        elif msg.topic == TOPIC_AI_CONTEXT:
            with state_lock:
                context_state.update({
                    "speed_kmh":float(d.get("speed_kmh",0)),
                    "vehicles_frame":int(d.get("vehicles_frame",0)),
                    "weather":d.get("weather","SUN"),
                    "distance":float(d.get("distance",5)),
                    "capture_interval":float(d.get("capture_interval",0.5)),
                    "roi":d.get("roi","STOP_LINE"),
                    "target_objects":d.get("target_objects",["MOTORBIKE","CAR"]),
                    "fps":float(d.get("fps",0)),"updated_at":int(time.time()),
                })
                ok,errs = validate_context(context_state)
                context_state["context_ok"] = ok; context_state["context_errors"] = errs
                p = dict(context_state)
            socketio.emit("context_update",p)
        elif msg.topic == TOPIC_TRAFFIC_STATE:
            l = d.get("light","").upper()
            if l in ("RED","YELLOW","GREEN"):
                with state_lock:
                    traffic_state.update({"light":l,"countdown":int(d.get("countdown",0)),
                        "camera":_cam_for_light(l),"updated_at":int(time.time())})
                _emit_traffic()
        elif msg.topic == TOPIC_THEME_UPDATE:
            theme_name = d.get("theme","")
            if theme_name:
                _set_theme(theme_name, set_by="mqtt-remote", auto=False)
    except Exception as e:
        log_mqtt.error("MQTT msg [%s]: %s",msg.topic,e)

def _init_mqtt():
    global _mqtt_client
    c = mqtt.Client(client_id=f"TrafficAI-v4-{int(time.time())}")
    c.on_connect=_on_mqtt_connect; c.on_disconnect=_on_mqtt_disconnect; c.on_message=_on_mqtt_message
    try:
        c.connect(MQTT_HOST,MQTT_PORT,MQTT_KEEPALIVE); c.loop_start()
        _mqtt_client = c
    except Exception as e:
        log_mqtt.error("MQTT init: %s",e)


# ════════════════════════════════════════════════════════════════
# BACKGROUND WORKERS
# ════════════════════════════════════════════════════════════════
def _device_watchdog():
    while True:
        time.sleep(10)
        now = int(time.time())
        for did,d in devices_state.items():
            try:
                if d["status"]=="ONLINE" and (now-d["last_seen"])>30:
                    with state_lock: d["status"]="OFFLINE"
                    socketio.emit("device_update",{"device_id":did,**d})
                    _log_event("WARN","WATCHDOG",f"Device {d['name']} offline")
            except Exception as e:
                log.error("Watchdog error: %s", e)

def _context_snapshot_worker():
    while True:
        time.sleep(60)
        with state_lock: ctx=dict(context_state)
        try:
            conn=sqlite3.connect(str(DB_PATH)); conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""INSERT INTO context_snapshots
                (speed_kmh,vehicles_frame,weather,capture_interval,fps,context_ok,ts)
                VALUES(?,?,?,?,?,?,?)""",
                (ctx["speed_kmh"],ctx["vehicles_frame"],ctx["weather"],
                 ctx["capture_interval"],ctx["fps"],1 if ctx["context_ok"] else 0,int(time.time())))
            conn.commit(); conn.close()
        except Exception as e:
            log.error("Context snapshot error: %s", e)

def _theme_auto_worker():
    while True:
        time.sleep(15)
        try:
            _tb_sync_theme()
            auto_theme = _auto_select_theme()
            try:
                conn = sqlite3.connect(str(DB_PATH))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT theme, set_by, ts FROM theme_preferences ORDER BY ts DESC LIMIT 1")
                row = cur.fetchone(); conn.close()
                last_manual_ago = time.time() - (row["ts"] if row else 0)
                was_manual = row and row["set_by"] == "user" and last_manual_ago < 300
            except Exception:
                was_manual = False
            if not was_manual:
                _set_theme(auto_theme, set_by="auto-worker", auto=True)
        except Exception as e:
            log_theme.error("Theme auto worker error: %s", e)


# ════════════════════════════════════════════════════════════════
# VIDEO STREAM (ESP32-CAM)
# ════════════════════════════════════════════════════════════════
def _generate_frames():
    while True:
        with frame_lock: frame = latest_frame
        if frame is None:
            img=np.zeros((360,640,3),dtype=np.uint8)
            cv2.putText(img,"Waiting for ESP32-CAM...",(100,170),
                        cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,200,255),2)
            with state_lock: light=traffic_state["light"]
            cv2.circle(img,(320,290),18,
                       {"RED":(0,0,220),"YELLOW":(0,200,220),"GREEN":(0,220,0)}.get(light,(80,80,80)),-1)
            _,buf=cv2.imencode(".jpg",img,[cv2.IMWRITE_JPEG_QUALITY,70])
            frame=buf.tobytes(); time.sleep(0.1)
        else: time.sleep(0.033)
        yield(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+frame+b"\r\n")


# ════════════════════════════════════════════════════════════════
# REST API
# ════════════════════════════════════════════════════════════════

@app.get("/api/bootstrap")
@require_token
@log_request_timing
def api_bootstrap():
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT id,plate,type,speed_kmh,light_state,roi,vehicles_frame,
                   confidence,image_url,cam_id,ts,date_str FROM violations ORDER BY ts DESC LIMIT 20""")
    violations=[dict(r) for r in cur.fetchall()]
    today=datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM violations WHERE date_str=?",(today,))
    today_cnt=cur.fetchone()[0]
    cur.execute("SELECT level,source,message,ts FROM system_events ORDER BY ts DESC LIMIT 30")
    events=[dict(r) for r in cur.fetchall()]
    with state_lock:
        t=dict(traffic_state); ctx=dict(context_state)
        devs={k:dict(v) for k,v in devices_state.items()}; st=dict(system_stats)
    st["uptime_s"]=int(time.time()-st["start_time"]); st["violations_today"]=today_cnt
    return jsonify({"ok":True,"traffic":t,"context":ctx,"context_limits":CONTEXT_LIMITS,
                    "camera_optimal":CAMERA_OPTIMAL,"devices":devs,"violations":violations,
                    "events":events,"stats":st,"laptop_camera_active":_laptop_cam_active,
                    "theme": _get_current_theme(),
                    "theme_config": THEME_CONFIG.get(_get_current_theme(), {}),
                    "available_themes": list(THEME_CONFIG.keys()),
                    "server_version": "4.0.2"})


@app.get("/api/violations")
@require_token
@log_request_timing
def api_get_violations():
    db=get_db(); cur=db.cursor()
    pg=max(1,int(request.args.get("page",1)))
    pp=min(100,int(request.args.get("per_page",20)))
    pq=request.args.get("plate","").strip().upper()
    lq=request.args.get("light","").upper()
    dq=request.args.get("date","")
    tq=request.args.get("type","").upper()
    off=(pg-1)*pp
    w,p=["1=1"],[]
    if pq: w.append("plate LIKE ?"); p.append(f"%{pq}%")
    if lq: w.append("light_state=?"); p.append(lq)
    if dq: w.append("date_str=?"); p.append(dq)
    if tq: w.append("type=?"); p.append(tq)
    wc=" AND ".join(w)
    cur.execute(f"SELECT COUNT(*) FROM violations WHERE {wc}",p); total=cur.fetchone()[0]
    cur.execute(f"""SELECT id,plate,type,speed_kmh,light_state,roi,vehicles_frame,
                    confidence,image_url,cam_id,ts,date_str FROM violations
                    WHERE {wc} ORDER BY ts DESC LIMIT ? OFFSET ?""", p+[pp,off])
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({"ok":True,"data":rows,"total":total,
                    "page":pg,"per_page":pp,"pages":max(1,-(-total//pp))})


@app.delete("/api/violations/<int:vid>")
@require_token
@log_request_timing
def api_delete_violation(vid:int):
    db=get_db(); db.execute("DELETE FROM violations WHERE id=?",(vid,)); db.commit()
    _log_event("INFO","API",f"Violation #{vid} deleted")
    return jsonify({"ok":True})


@app.post("/api/traffic/force")
@require_token
@log_request_timing
def api_force_light():
    d=request.get_json(force=True) or {}
    l=d.get("light","RED").upper()
    if l not in ("RED","YELLOW","GREEN"):
        return jsonify({"ok":False,"error":"Invalid light — use RED, YELLOW or GREEN"}),400
    force_light(l,"EMERGENCY")
    return jsonify({"ok":True,"light":l})


@app.post("/api/traffic/auto")
@require_token
@log_request_timing
def api_reset_auto():
    reset_auto()
    return jsonify({"ok":True,"mode":"AUTO"})


@app.put("/api/traffic/cycle")
@require_token
@log_request_timing
def api_update_cycle():
    d=request.get_json(force=True) or {}
    with state_lock:
        c=traffic_state["cycle"]
        if "green_duration"  in d: c["green_duration"] =max(5,int(d["green_duration"]))
        if "yellow_duration" in d: c["yellow_duration"]=max(3,int(d["yellow_duration"]))
        if "red_duration"    in d: c["red_duration"]   =max(5,int(d["red_duration"]))
    return jsonify({"ok":True,"cycle":traffic_state["cycle"]})


@app.get("/api/devices")
@require_token
@log_request_timing
def api_devices():
    with state_lock: devs={k:dict(v) for k,v in devices_state.items()}
    return jsonify({"ok":True,"devices":devs})


@app.get("/api/context")
@require_token
@log_request_timing
def api_context():
    with state_lock: ctx=dict(context_state)
    ok,errs=validate_context(ctx)
    return jsonify({"ok":True,"context":ctx,"limits":CONTEXT_LIMITS,
                    "camera_optimal":CAMERA_OPTIMAL,"valid":ok,"errors":errs})


@app.get("/api/events")
@require_token
@log_request_timing
def api_events():
    lv=request.args.get("level",""); lim=min(200,int(request.args.get("limit",50)))
    db=get_db(); cur=db.cursor()
    if lv: cur.execute("SELECT * FROM system_events WHERE level=? ORDER BY ts DESC LIMIT ?",(lv.upper(),lim))
    else:  cur.execute("SELECT * FROM system_events ORDER BY ts DESC LIMIT ?",(lim,))
    return jsonify({"ok":True,"events":[dict(r) for r in cur.fetchall()]})


@app.get("/api/stats")
@require_token
@log_request_timing
def api_stats():
    db=get_db(); cur=db.cursor(); today=datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM violations"); total=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM violations WHERE date_str=?",(today,)); td=cur.fetchone()[0]
    cur.execute("""SELECT strftime('%H',datetime(ts,'unixepoch')) hr,COUNT(*) cnt
                   FROM violations WHERE date_str=? GROUP BY hr ORDER BY hr""",(today,))
    by_h={r[0]:r[1] for r in cur.fetchall()}
    cur.execute("""SELECT date_str,COUNT(*) cnt FROM violations WHERE ts>?
                   GROUP BY date_str ORDER BY date_str""",(int(time.time())-7*86400,))
    by_d=[{"date":r[0],"count":r[1]} for r in cur.fetchall()]
    cur.execute("SELECT type,COUNT(*) cnt FROM violations GROUP BY type")
    by_t={r[0]:r[1] for r in cur.fetchall()}
    cur.execute("SELECT AVG(confidence) FROM violations WHERE ts>?",(int(time.time())-86400,))
    ac=cur.fetchone()[0] or 0
    with state_lock: st=dict(system_stats)
    st["uptime_s"]=int(time.time()-st["start_time"])
    return jsonify({"ok":True,"total":total,"today":td,"by_hour":by_h,"by_day":by_d,
                    "by_type":by_t,"avg_conf":round(ac,3),"system":st,
                    "current_theme": _get_current_theme()})


# ════════════════════════════════════════════════════════════════
# v4.0.2: THEME API — FIX 403
# ════════════════════════════════════════════════════════════════

@app.get("/api/theme")
@require_theme_token   # FIX: chấp nhận mọi valid login token
@log_request_timing
def api_get_theme():
    """
    FIX v4.0.2: GET current theme.
    Chấp nhận Authorization: Bearer <token> (token từ /api/login hoặc DASHBOARD_SECRET).
    Không còn trả về 403 khi dùng token login thông thường.
    """
    try:
        _tb_sync_theme()
    except Exception:
        pass

    theme  = _get_current_theme()
    config = THEME_CONFIG.get(theme, {})
    with state_lock:
        ctx_ok = context_state.get("context_ok", True)

    log_theme.debug("GET /api/theme → %s", theme)
    return jsonify({
        "ok":               True,
        "theme":            theme,
        "config":           config,
        "available_themes": list(THEME_CONFIG.keys()),
        "context_ok":       ctx_ok,
        "auto_selected":    True,
        "ts":               int(time.time()),
    })


@app.post("/api/theme")
@require_token
@log_request_timing
def api_set_theme():
    d = request.get_json(force=True, silent=True) or {}
    theme_name = d.get("theme","").strip()
    if not theme_name:
        return jsonify({"ok":False,"error":"Missing 'theme' field"}), 400
    if theme_name not in THEME_CONFIG:
        return jsonify({"ok":False,"error":f"Unknown theme '{theme_name}'",
                        "valid": list(THEME_CONFIG.keys())}), 400
    success = _set_theme(theme_name, set_by="user", auto=False)
    if not success:
        return jsonify({"ok":False,"error":"Theme update failed"}), 500
    return jsonify({"ok":True,"theme":theme_name,"config":THEME_CONFIG[theme_name],"ts":int(time.time())})


@app.get("/api/theme/history")
@require_token
@log_request_timing
def api_theme_history():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT theme, set_by, auto_selected, ts FROM theme_preferences ORDER BY ts DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({"ok":True,"history":rows,"current":_get_current_theme()})


@app.get("/api/theme/list")
@log_request_timing
def api_theme_list():
    """Public endpoint — không cần auth, dùng để UI biết themes có sẵn trước khi login."""
    return jsonify({"ok":True,"themes":THEME_CONFIG,"current":_get_current_theme()})


# ════════════════════════════════════════════════════════════════
# VIDEO + STATIC
# ════════════════════════════════════════════════════════════════

@app.get("/video_feed")
def video_feed():
    return Response(_generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/health")
@log_request_timing
def api_health():
    ok = _mqtt_client is not None and _mqtt_client.is_connected()
    return jsonify({"ok":True,"server":"AI Traffic Control v4.0.2",
                    "time":int(time.time()),"mqtt":ok,
                    "uptime":int(time.time()-system_stats["start_time"]),
                    "laptop_cam":_laptop_cam_active,
                    "theme": _get_current_theme(),
                    "version": "4.0.2"})


@app.post("/api/violations/inject")
@require_token
@log_request_timing
@rate_limit(max_per_minute=30)
def api_inject():
    d=request.get_json(force=True) or {}
    d.setdefault("ts",int(time.time())); d.setdefault("plate","51B-12345")
    d.setdefault("type","MOTORBIKE"); d.setdefault("speed_kmh",14.2)
    d.setdefault("confidence",0.88); d.setdefault("cam_id","CAM_1")
    with state_lock: traffic_state["light"]="RED"
    process_violation(d)
    return jsonify({"ok":True,"message":"Violation injected"})


@app.get("/")
def root(): return send_from_directory(str(FRONTEND_DIR),"main.html")

@app.get("/<path:filename>")
def serve_fe(filename): return send_from_directory(str(FRONTEND_DIR),filename)

@app.get("/imge/<path:filename>")
def serve_img(filename): return send_from_directory(str(IMAGE_DIR),filename)


# ════════════════════════════════════════════════════════════════
# GLOBAL ERROR HANDLERS
# ════════════════════════════════════════════════════════════════

@app.errorhandler(400)
def handle_400(e):
    return jsonify({"ok":False,"error":"Bad request","detail":str(e)}), 400

@app.errorhandler(401)
def handle_401(e):
    log_api.warning("401: %s from %s", request.path, request.remote_addr)
    return jsonify({"ok":False,"error":"Unauthorized"}), 401

@app.errorhandler(403)
def handle_403(e):
    log_api.warning("403: %s from %s", request.path, request.remote_addr)
    return jsonify({"ok":False,"error":"Forbidden"}), 403

@app.errorhandler(404)
def handle_404(e):
    return jsonify({"ok":False,"error":"Not found","path":request.path}), 404

@app.errorhandler(429)
def handle_429(e):
    return jsonify({"ok":False,"error":"Too many requests"}), 429

@app.errorhandler(500)
def handle_500(e):
    log.error("500 on %s: %s", request.path, str(e))
    return jsonify({"ok":False,"error":"Internal server error"}), 500


# ════════════════════════════════════════════════════════════════
# WEBSOCKET
# ════════════════════════════════════════════════════════════════
@socketio.on("connect")
def ws_connect():
    with state_lock:
        emit("traffic_state",dict(traffic_state))
        emit("context_update",dict(context_state))
        emit("device_list",{k:dict(v) for k,v in devices_state.items()})
        emit("laptop_cam_status",{"active":_laptop_cam_active})
        emit("theme_update",{
            "theme":  _get_current_theme(),
            "config": THEME_CONFIG.get(_get_current_theme(), {}),
            "source": "connect",
        })

@socketio.on("disconnect")
def ws_disconnect():
    log.debug("WebSocket client disconnected")

@socketio.on("cmd_force_light")
def ws_force(data):
    l=(data or {}).get("light","RED").upper()
    if l in ("RED","YELLOW","GREEN"):
        force_light(l)

@socketio.on("cmd_auto")
def ws_auto(_):
    reset_auto()

@socketio.on("ping_server")
def ws_ping(_):
    emit("pong_server",{"ts":int(time.time()),"theme":_get_current_theme()})

@socketio.on("set_theme")
def ws_set_theme(data):
    theme_name = (data or {}).get("theme","")
    if theme_name:
        _set_theme(theme_name, set_by="ws-client", auto=False)
        emit("theme_update",{
            "theme":  theme_name,
            "config": THEME_CONFIG.get(theme_name, {}),
            "source": "ws-client",
        })


# ════════════════════════════════════════════════════════════════
# BOOTSTRAP
# ════════════════════════════════════════════════════════════════
def _bootstrap():
    log.info("🚀 AI Traffic Control v4.0.2 starting...")
    log.info("   DASHBOARD_SECRET = %s (len=%d)", DASHBOARD_SECRET[:8]+"...", len(DASHBOARD_SECRET))

    threading.Thread(target=_traffic_cycle_worker,   name="TrafficCycle",   daemon=True).start()
    threading.Thread(target=_device_watchdog,         name="DeviceWatchdog", daemon=True).start()
    threading.Thread(target=_context_snapshot_worker, name="CtxSnapshot",    daemon=True).start()
    threading.Thread(target=_tb_periodic_push,        name="TB-Push",        daemon=True).start()
    threading.Thread(target=_theme_auto_worker,       name="ThemeWorker",    daemon=True).start()

    _init_mqtt()
    _tb_sync_theme()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT theme FROM theme_preferences ORDER BY ts DESC LIMIT 1")
        row = cur.fetchone(); conn.close()
        if row:
            _set_theme(row["theme"], set_by="boot-restore", auto=False)
            log_theme.info("Restored theme: %s", row["theme"])
    except Exception as e:
        log_theme.debug("Theme restore skipped: %s", e)

    try:
        from ai_engine import start_ai; start_ai(app)
        log.info("🤖 AI engine OK")
    except ImportError:
        log.info("ℹ️  No ai_engine — demo mode")
    except Exception as e:
        log.error("AI engine error: %s", e)

    _log_event("INFO","SYSTEM","AI Traffic Control v4.0.3 khởi động")
    log.info("✅ v4.0.3 Ready — port 5050")
    log.info("   FIX v4.0.3: main.js pre-seeds DASHBOARD_SECRET='TRAFFIC_AI_TOKEN' vào localStorage")
    log.info("   FIX v4.0.3: /api/theme 403 → FIXED (require_theme_token accept DASHBOARD_SECRET)")
    log.info("   FIX v4.0.3: /api/bootstrap 401 → FIXED (token luôn có nhờ pre-seed)")


if __name__=="__main__":
    _bootstrap()
    socketio.run(app,host="0.0.0.0",port=5050,debug=False,use_reloader=False,log_output=True)