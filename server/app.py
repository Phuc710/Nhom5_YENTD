"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI TRAFFIC CONTROL — PREMIUM BACKEND SERVER v6.0 (2026)                   ║
║  Flask + SocketIO + MQTT + SQLite + AI Engine + ESP32 + Dual Camera        ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │  CAMERA ARCHITECTURE — 2 STREAMS ĐỘC LẬP                           │    ║
║  │                                                                     │    ║
║  │  📷 Camera Laptop  (/laptop_feed)                                   │    ║
║  │     • app.py owns VideoCapture(0)                                   │    ║
║  │     • Stream riêng cho khách hàng test / demo                       │    ║
║  │     • Luôn chạy 30fps, overlay HUD realtime                        │    ║
║  │     • Không phụ thuộc ESP32                                        │    ║
║  │                                                                     │    ║
║  │  📡 Camera Live    (/video_feed)                                    │    ║
║  │     • ai_engine owns detection                                      │    ║
║  │     • Chưa có ESP32 → webcam làm fallback (DEMO mode)              │    ║
║  │     • Có ESP32 kết nối → switch ESP32-CAM ngay lập tức (REAL mode) │    ║
║  │     • Cả 2 cameras chạy song song bình thường sau khi có ESP32     │    ║
║  │                                                                     │    ║
║  │  ✅ Không conflict — 2 nhiệm vụ khác nhau, 2 stream khác nhau      │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  PUBLIC API — app ↔ ai_engine (0 fragile import):                          ║
║    app.set_ai_frame(bytes)          ← ai_engine push detection frame       ║
║    app.get_current_light() → str   ← ai_engine đọc đèn traffic            ║
║    app.update_ai_context(v, fps)   ← ai_engine update context + emit      ║
║    app.process_violation(payload)  ← ai_engine gửi vi phạm                ║
║                                                                              ║
║  VERSION HISTORY:                                                            ║
║    v5.0  Traffic cycle + AI engine integration + DEMO/REAL mode           ║
║    v5.1  set_ai_frame() + FRONTEND_DIR auto-create + EasyOCR offline     ║
║    v5.2  get_current_light() + update_ai_context() (0 fragile import)    ║
║    v5.3  grab()+retrieve() + BUFFERSIZE=1 + pre-fill + FPS fix           ║
║    v6.0  Full rewrite: clean architecture, dual stream confirmed,         ║
║          enhanced HUD, laptop FPS emit via SocketIO, connection           ║
║          quality indicator, improved demo frames, full API docs           ║
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

# ════════════════════════════════════════════════════════════════════════════
# LOGGING — Rotating file + console + errors
# ════════════════════════════════════════════════════════════════════════════
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_fmt_console = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
_fmt_file    = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s")

_h_console = logging.StreamHandler()
_h_console.setLevel(logging.INFO)
_h_console.setFormatter(_fmt_console)

_h_file = logging.handlers.RotatingFileHandler(
    str(LOG_DIR / "app.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8"
)
_h_file.setLevel(logging.DEBUG)
_h_file.setFormatter(_fmt_file)

_h_error = logging.handlers.RotatingFileHandler(
    str(LOG_DIR / "errors.log"), maxBytes=500_000, backupCount=3, encoding="utf-8"
)
_h_error.setLevel(logging.ERROR)
_h_error.setFormatter(_fmt_file)

logging.basicConfig(level=logging.DEBUG, handlers=[_h_console])

def _make_logger(name: str) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.DEBUG)
    for h in (_h_file, _h_error):
        lg.addHandler(h)
    lg.propagate = False
    return lg

log        = _make_logger("TrafficAI")
log_theme  = _make_logger("TrafficAI.Theme")
log_tb     = _make_logger("TrafficAI.ThingsBoard")
log_laptop = _make_logger("TrafficAI.LaptopCam")
log_mqtt   = _make_logger("TrafficAI.MQTT")
log_api    = _make_logger("TrafficAI.API")
log_viol   = _make_logger("TrafficAI.Violation")
log_ai     = _make_logger("TrafficAI.AI")

# ════════════════════════════════════════════════════════════════════════════
# PATHS & DIRECTORIES
# ════════════════════════════════════════════════════════════════════════════
BASE_DIR     = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "DEVELOPER"
IMAGE_DIR    = PROJECT_ROOT / "imge"
DB_PATH      = BASE_DIR / "traffic_ai.db"

IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# Auto-create DEVELOPER/ with premium placeholder if missing
if not FRONTEND_DIR.exists():
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    (FRONTEND_DIR / "main.html").write_text("""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Traffic Control v6.0 — Setup Required</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;800&display=swap');
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#070c1a;color:#20caff;font-family:'Space Mono',monospace;
         display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}
    .card{border:1px solid #20caff33;border-radius:16px;padding:56px;max-width:680px;
          background:linear-gradient(135deg,rgba(32,202,255,.06),rgba(0,232,122,.03));
          box-shadow:0 0 60px rgba(32,202,255,.12),0 0 120px rgba(32,202,255,.04)}
    h1{font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
       background:linear-gradient(90deg,#20caff,#00e87a);-webkit-background-clip:text;
       -webkit-text-fill-color:transparent;margin-bottom:12px}
    .version{font-size:.75rem;color:#20caff88;letter-spacing:3px;margin-bottom:28px}
    p{color:#7aaccc;line-height:1.8;margin:10px 0}
    code{background:rgba(32,202,255,.12);border-radius:4px;padding:2px 10px;
         font-size:.9rem;color:#00e87a;border:1px solid #00e87a22}
    ul{text-align:left;margin:20px 0;padding-left:24px;color:#7aaccc}
    li{margin:8px 0;list-style:none;padding-left:8px}
    li::before{content:"→ ";color:#20caff}
    .badge{display:inline-flex;align-items:center;gap:8px;margin-top:28px;
           background:rgba(0,232,122,.1);border:1px solid #00e87a33;
           border-radius:999px;padding:8px 20px;font-size:.75rem;
           color:#00e87a;letter-spacing:1.5px}
    .dot{width:8px;height:8px;border-radius:50%;background:#00e87a;
         animation:pulse 2s ease infinite}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
  </style>
</head>
<body>
<div class="card">
  <h1>⚡ AI TRAFFIC CONTROL</h1>
  <div class="version">VERSION 6.0 — 2026</div>
  <p>Backend server đang chạy. Frontend chưa được deploy.</p>
  <p>Đặt các file frontend vào thư mục: <code>PROJECT_ROOT/DEVELOPER/</code></p>
  <ul>
    <li>main.html — Giao diện chính dashboard</li>
    <li>API sẵn sàng tại <code>/api/health</code></li>
    <li>WebSocket tại <code>ws://localhost:5050</code></li>
    <li>Camera Laptop stream: <code>/laptop_feed</code></li>
    <li>Camera Live (ESP32): <code>/video_feed</code></li>
    <li>Token mặc định: <code>TRAFFIC_AI_TOKEN</code></li>
  </ul>
  <div class="badge"><span class="dot"></span>BACKEND ONLINE</div>
</div>
</body>
</html>""", encoding="utf-8")
    log.warning("⚠️  DEVELOPER/ created with placeholder — deploy frontend here: %s", FRONTEND_DIR)
elif not (FRONTEND_DIR / "main.html").exists():
    log.warning("⚠️  DEVELOPER/main.html not found — place it at: %s", FRONTEND_DIR)

# ════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT & CONSTANTS
# ════════════════════════════════════════════════════════════════════════════
MQTT_HOST  = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT  = int(os.getenv("MQTT_PORT", 1883))
MQTT_KEEPALIVE = 60

# MQTT topics
TOPIC_ESP32_STATUS  = "traffic/esp32/status"
TOPIC_ESP32_FRAME   = "traffic/esp32/frame"
TOPIC_AI_VIOLATION  = "traffic/ai/violation"
TOPIC_AI_CONTEXT    = "traffic/ai/context"
TOPIC_TRAFFIC_STATE = "traffic/light/state"
TOPIC_CMD_LIGHT     = "traffic/cmd/light"
TOPIC_CMD_EMERGENCY = "traffic/cmd/emergency"
TOPIC_THEME_UPDATE  = "traffic/ui/theme"

# ThingsBoard
TB_HOST         = os.getenv("TB_HOST", "http://localhost:8080")
TB_ACCESS_TOKEN = os.getenv("TB_TOKEN", "")

# Auth
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "TRAFFIC_AI_TOKEN")
THEME_TOKEN      = os.getenv("THEME_TOKEN", "premium-2026")
_ADMIN_USER      = "admin"
_ADMIN_PASS      = "admin123"
_ADMIN_ROLE      = "superadmin"
_TOKEN_TTL       = 28_800  # 8 hours

# ════════════════════════════════════════════════════════════════════════════
# THEME CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════
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
    "ocean-blue": {
        "colors": {"primary": "#0ea5e9", "secondary": "#6366f1", "accent": "#f59e0b", "bg": "#040d18"},
        "fonts": "Space Mono, IBM Plex Mono",
        "particles": {"color": "#0ea5e9", "line_color": "#6366f1", "count": 55},
        "description": "Deep ocean — calm monitoring mode",
    },
}

_current_theme = "neon-futuristic"
_theme_lock    = threading.Lock()

# ════════════════════════════════════════════════════════════════════════════
# CONTEXT LIMITS (ESP32 optimal specs)
# ════════════════════════════════════════════════════════════════════════════
CONTEXT_LIMITS = {
    "speed_kmh":        {"max": 20,            "unit": "km/h", "label": "Vận tốc"},
    "vehicles_frame":   {"max": 6,             "unit": "xe",   "label": "Phương tiện/khung"},
    "weather":          {"allowed": ["SUN","LIGHT_RAIN","CLOUDY"], "unit":"","label":"Thời tiết"},
    "distance":         {"optimal": 5,         "unit": "m",    "label": "Khoảng cách"},
    "roi":              {"value": "STOP_LINE", "unit": "",     "label": "Vùng ROI"},
    "capture_interval": {"max": 0.5,           "unit": "s",    "label": "Tốc độ chụp"},
    "target_objects":   {"allowed": ["MOTORBIKE","CAR"], "unit":"","label":"Đối tượng"},
}

CAMERA_OPTIMAL = {
    "frame_size": "FRAMESIZE_XGA", "jpeg_quality": 8, "fb_count": 2,
    "ae_level": -2, "gainceiling": "GAINCEILING_4X", "contrast": 1,
    "sharpness": 2, "denoise": 1, "xclk_freq_hz": 20_000_000,
}

# ════════════════════════════════════════════════════════════════════════════
# FLASK APP + SOCKETIO
# ════════════════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "traffic-ai-secret-v6-2026")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                    logger=False, engineio_logger=False)

# ════════════════════════════════════════════════════════════════════════════
# SHARED STATE — all protected by state_lock (RLock for re-entrant safety)
# ════════════════════════════════════════════════════════════════════════════
state_lock = threading.RLock()

traffic_state = {
    "light": "RED", "phase": "ĐỎ", "countdown": 30,
    "mode": "AUTO", "camera": "ACTIVE",
    "cycle": {"green_duration": 30, "yellow_duration": 5, "red_duration": 30},
    "updated_at": int(time.time()),
}

context_state = {
    "speed_kmh": 0.0, "vehicles_frame": 0, "weather": "SUN",
    "distance": 5.0, "capture_interval": 0.5, "roi": "STOP_LINE",
    "target_objects": ["MOTORBIKE", "CAR"],
    "fps": 0.0, "violations_today": 0, "updated_at": int(time.time()),
    "context_ok": True, "context_errors": [],
    "ai_mode": "DEMO",        # "DEMO" | "REAL" | "NO_AI"
    "esp32_connected": False,
    "models_ready": False,
    "laptop_fps": 0.0,        # v6.0: realtime laptop FPS
    "detection_fps": 0.0,     # v6.0: ai detection FPS
}

devices_state = {
    "esp32_cam_1": {"name":"ESP32-CAM #1","ip":"192.168.1.101","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_cam_2": {"name":"ESP32-CAM #2","ip":"192.168.1.102","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_cam_3": {"name":"ESP32-CAM #3","ip":"192.168.1.103","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_main":  {"name":"ESP32 Main",  "ip":"192.168.1.110","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
    "esp32_led":   {"name":"LED 7 Đoạn", "ip":"192.168.1.111","status":"OFFLINE","signal":0,"temp":0,"uptime":0,"last_seen":0,"fw":""},
}

# ESP32 Camera Live frame buffer (populated by ai_engine via MQTT)
latest_frame: bytes | None = None
frame_lock = threading.Lock()

system_stats = {
    "start_time": time.time(), "violations_total": 0, "violations_today": 0,
    "frames_processed": 0, "mqtt_messages": 0, "ai_detections": 0,
    "version": "6.0",
}

# ════════════════════════════════════════════════════════════════════════════
# ██████████████  CAMERA LAPTOP MODULE  ████████████████████████████████████
# ════════════════════════════════════════════════════════════════════════════
#
# Camera Laptop = app.py owns VideoCapture(0)
# Stream /laptop_feed  → test demo cho khách hàng
# app.py không xử lý AI — chỉ stream video + HUD overlay
#
# Camera Live    = ai_engine owns detection
# Stream /video_feed   → khi có ESP32: ESP32-CAM qua MQTT
#                      → khi không có: webcam fallback cho YOLO detection
#
# Cả 2 có thể mở VideoCapture(0) song song (Linux/Mac/most Windows drivers OK)
# Nếu Windows driver không cho phép multi-open → ai_engine dùng demo frames,
# Camera Laptop vẫn hoạt động bình thường.
#
# ════════════════════════════════════════════════════════════════════════════

_laptop_cam_active = False
_laptop_cam_thread = None
_laptop_frame: bytes | None = None
_laptop_frame_lock = threading.Lock()
_laptop_cam_stop   = threading.Event()
_LAPTOP_W, _LAPTOP_H = 1280, 720

# v6.0: FPS tracking for laptop stream
_laptop_fps_value = 0.0
_laptop_fps_lock  = threading.Lock()


def set_ai_frame(frame_bytes: bytes) -> None:
    """
    PUBLIC API v5.1+ — ai_engine pushes detection-overlay frames here.
    These frames appear on Camera Laptop stream overlaid with YOLO bounding boxes.
    Thread-safe. Called from ai_engine._update_app_frame().
    """
    global _laptop_frame
    with _laptop_frame_lock:
        _laptop_frame = frame_bytes


def _draw_overlay(frame: np.ndarray) -> np.ndarray:
    """
    Draw full HUD overlay on Camera Laptop frame.
    Shows: timestamp, traffic light, countdown, ROI line,
           mode indicator (DEMO/REAL/ESP32), vehicle count, FPS.
    """
    h, w = frame.shape[:2]

    # ── Top bar background ───────────────────────────────────────
    bar = frame.copy()
    cv2.rectangle(bar, (0, 0), (w, 34), (4, 8, 18), -1)
    cv2.addWeighted(bar, 0.75, frame, 0.25, 0, frame)

    # ── Timestamp ────────────────────────────────────────────────
    ts_str = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
    cv2.putText(frame, ts_str, (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 220, 255), 1, cv2.LINE_AA)

    with state_lock:
        light    = traffic_state["light"]
        cam_st   = traffic_state["camera"]
        cntdown  = traffic_state["countdown"]
        veh      = context_state["vehicles_frame"]
        ai_mode  = context_state["ai_mode"]
        esp32_ok = context_state["esp32_connected"]

    # ── Traffic light indicator (top-right) ──────────────────────
    light_colors = {"RED": (0,0,220), "YELLOW": (0,190,220), "GREEN": (0,200,60)}
    lc = light_colors.get(light, (80, 80, 80))
    cv2.circle(frame, (w - 22, 17), 11, lc, -1)
    cv2.circle(frame, (w - 22, 17), 11, (255, 255, 255), 1)

    light_vi = {"RED": "ĐỎ", "YELLOW": "VÀNG", "GREEN": "XANH"}.get(light, light)
    cv2.putText(frame, f"{light_vi} {cntdown}s",
                (w - 195, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 230, 255), 1, cv2.LINE_AA)

    # ── ROI / STOP LINE ──────────────────────────────────────────
    roi_y = int(h * 0.72)
    roi_color = {"RED": (50,50,220), "GREEN": (50,180,50), "YELLOW": (50,150,200)}.get(light, (80,80,80))
    cv2.line(frame, (int(w*0.04), roi_y), (int(w*0.96), roi_y), roi_color, 2)
    cv2.putText(frame, "STOP LINE — ROI",
                (int(w*0.30), roi_y - 7),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, roi_color, 1, cv2.LINE_AA)

    # ── Bottom status bar ────────────────────────────────────────
    cv2.rectangle(frame, (0, h - 30), (w, h), (4, 8, 18), -1)

    mode_color = (0, 200, 80) if esp32_ok else (0, 120, 220)
    mode_txt = f"{'ESP32-LIVE' if esp32_ok else 'DEMO'} | AI:{ai_mode} | CAM:{cam_st}"
    cv2.putText(frame, mode_txt, (8, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, mode_color, 1, cv2.LINE_AA)

    # Vehicle count + FPS (right side)
    with _laptop_fps_lock:
        fps_val = _laptop_fps_value
    cv2.putText(frame, f"FPS:{fps_val:.0f}  Xe:{veh}/6",
                (w - 175, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 200, 255), 1, cv2.LINE_AA)

    return frame


def _generate_demo_frame_laptop(fidx: int) -> np.ndarray:
    """
    High-quality animated demo frame for Camera Laptop when no webcam available.
    Shows moving vehicles with license plates, road scene, and DEMO watermark.
    """
    W, H = _LAPTOP_W, _LAPTOP_H
    frame = np.zeros((H, W, 3), dtype=np.uint8)

    # Sky gradient
    for y in range(int(H * 0.55)):
        ratio = y / (H * 0.55)
        b = int(28 - ratio * 18)
        g = int(18 - ratio * 8)
        r = int(10 - ratio * 5)
        frame[y, :] = (max(0,r), max(0,g), max(0,b))

    # Road surface
    cv2.rectangle(frame, (0, int(H*0.55)), (W, H), (22, 28, 36), -1)

    # Road lane markers
    for xi in range(0, W, 80):
        cv2.line(frame, (xi, int(H*0.72)), (xi+40, int(H*0.72)), (60, 70, 80), 2)

    # Animated vehicles
    t = time.time()
    vx1 = int((W * 0.06) + (fidx * 4) % int(W * 0.80))
    vy1 = int(H * 0.66)
    # Car 1 — blue sedan
    cv2.rectangle(frame, (vx1-38, vy1-22), (vx1+38, vy1+22), (50, 90, 190), -1)
    cv2.rectangle(frame, (vx1-38, vy1-22), (vx1+38, vy1+22), (80, 130, 220), 1)
    cv2.rectangle(frame, (vx1-25, vy1-32), (vx1+25, vy1-18), (40, 60, 120), -1)
    # Plate
    cv2.rectangle(frame, (vx1-26, vy1+8), (vx1+26, vy1+20), (220, 220, 60), -1)
    cv2.putText(frame, "51B-12345", (vx1-24, vy1+18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (30, 30, 30), 1)

    vx2 = int(W * 0.55 + (fidx * 2.5) % int(W * 0.38))
    vy2 = int(H * 0.70)
    # Car 2 — red motorbike
    cv2.rectangle(frame, (vx2-20, vy2-18), (vx2+20, vy2+18), (150, 40, 40), -1)
    cv2.rectangle(frame, (vx2-20, vy2-18), (vx2+20, vy2+18), (200, 60, 60), 1)
    cv2.rectangle(frame, (vx2-12, vy2+5), (vx2+12, vy2+16), (220, 220, 60), -1)
    cv2.putText(frame, "30A-99001", (vx2-11, vy2+14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.28, (30, 30, 30), 1)

    # DEMO watermark
    overlay_txt = frame.copy()
    cv2.putText(overlay_txt, "DEMO MODE",
                (int(W*0.34), int(H*0.40)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.8, (15, 25, 45), 4, cv2.LINE_AA)
    cv2.addWeighted(overlay_txt, 0.6, frame, 0.4, 0, frame)
    cv2.putText(frame, "Connect ESP32-CAM to switch LIVE detection",
                (int(W*0.18), int(H*0.48)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (30, 70, 120), 1, cv2.LINE_AA)

    return frame


def _laptop_cam_worker():
    """
    ┌──────────────────────────────────────────────────────────────┐
    │  Camera Laptop Worker — app.py owns VideoCapture(0)          │
    │                                                              │
    │  Nhiệm vụ: stream /laptop_feed cho khách hàng test          │
    │  Hoàn toàn độc lập với ai_engine                            │
    │  ai_engine có thể mở webcam song song cho detection          │
    │  (2 nhiệm vụ khác nhau, 2 stream khác nhau)                 │
    └──────────────────────────────────────────────────────────────┘

    v6.0 improvements:
    - grab() + retrieve() → luôn frame mới nhất (tránh stale buffer)
    - BUFFERSIZE=1 → giảm internal OpenCV latency
    - Pre-fill frame ngay khi open → không blank lúc đầu
    - Flush 3 stale frames sau khi open
    - FPS emit qua SocketIO mỗi 2s
    - demo frame quality nâng cấp
    """
    global _laptop_cam_active, _laptop_fps_value
    log_laptop.info("🎥 Camera Laptop worker starting (v6.0)...")

    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  _LAPTOP_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _LAPTOP_H)
        cap.set(cv2.CAP_PROP_FPS, 30)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # Giảm latency
        except Exception:
            pass

        # Flush stale frames từ buffer
        for _ in range(5):
            cap.grab()

        # Pre-fill frame ngay lập tức → stream không blank ban đầu
        ret, first_frame = cap.read()
        if ret and first_frame is not None:
            first_frame = _draw_overlay(first_frame)
            ok, buf = cv2.imencode(".jpg", first_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                with _laptop_frame_lock:
                    _laptop_frame = buf.tobytes()
        log_laptop.info("✅ Camera Laptop opened: %dx%d@30fps (VideoCapture(0))", _LAPTOP_W, _LAPTOP_H)
    else:
        cap.release()
        cap = None
        log_laptop.warning("⚠️  Camera Laptop: VideoCapture(0) not available → using demo frames")
        log_laptop.info("   (ai_engine may have opened the same webcam for detection — that is OK)")

    _laptop_cam_active = True
    fidx = 0
    fps_ts    = time.time()
    fps_count = 0
    fps_emit_ts = 0.0

    while not _laptop_cam_stop.is_set():
        try:
            if cap and cap.isOpened():
                # grab() first → discard stale, then retrieve() → fresh frame
                cap.grab()
                ret, frame = cap.retrieve()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue
            else:
                frame = _generate_demo_frame_laptop(fidx)
                fidx += 1

            frame = _draw_overlay(frame)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                with _laptop_frame_lock:
                    _laptop_frame = buf.tobytes()
                with state_lock:
                    system_stats["frames_processed"] += 1

            # FPS calculation + emit
            fps_count += 1
            now = time.time()
            elapsed = now - fps_ts
            if elapsed >= 2.0:
                fps_val = fps_count / elapsed
                fps_ts = now; fps_count = 0
                with _laptop_fps_lock:
                    _laptop_fps_value = fps_val
                # Emit FPS to frontend via SocketIO
                if now - fps_emit_ts >= 2.0:
                    socketio.emit("laptop_fps", {"fps": round(fps_val, 1)})
                    fps_emit_ts = now

        except Exception as e:
            log_laptop.error("Camera Laptop frame error: %s", e)

        time.sleep(0.025)  # ~40fps target (browser will receive ~30fps after encoding)

    if cap:
        cap.release()
    _laptop_cam_active = False
    log_laptop.info("🛑 Camera Laptop worker stopped")


def _gen_laptop_frames():
    """
    MJPEG generator for /laptop_feed stream.

    v6.0 fix: no sleep when frame is available → browser receives frames
    immediately → FPS counter shows correct value.
    Placeholder is same resolution (1280x720) as live frames → MJPEG
    parser doesn't get confused when switching.
    """
    # Pre-build placeholder (same resolution as live frames)
    _ph = np.zeros((_LAPTOP_H, _LAPTOP_W, 3), dtype=np.uint8)
    _ph[:] = (6, 10, 20)
    cv2.putText(_ph, "CAMERA LAPTOP",
                (int(_LAPTOP_W*0.34), int(_LAPTOP_H*0.44)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (16, 60, 140), 2, cv2.LINE_AA)
    cv2.putText(_ph, "Click BAT CAMERA to start stream",
                (int(_LAPTOP_W*0.27), int(_LAPTOP_H*0.54)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 90, 160), 1, cv2.LINE_AA)
    _, _ph_buf = cv2.imencode(".jpg", _ph, [cv2.IMWRITE_JPEG_QUALITY, 70])
    placeholder = _ph_buf.tobytes()

    BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"

    while True:
        with _laptop_frame_lock:
            frame = _laptop_frame

        if frame is None:
            yield BOUNDARY + placeholder + b"\r\n"
            time.sleep(0.1)
        else:
            yield BOUNDARY + frame + b"\r\n"
            time.sleep(0.033)  # ~30fps ceiling


@app.route("/laptop_feed")
def laptop_feed():
    return Response(_gen_laptop_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


# ════════════════════════════════════════════════════════════════════════════
# LAPTOP CAMERA API
# ════════════════════════════════════════════════════════════════════════════

@app.post("/api/laptop_camera/start")
def api_laptop_start():
    global _laptop_cam_thread
    auth = request.headers.get("Authorization", "")
    tok  = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if _laptop_cam_active:
        return jsonify({"ok": True, "status": "already_running"})
    _laptop_cam_stop.clear()
    _laptop_cam_thread = threading.Thread(target=_laptop_cam_worker, name="LaptopCam", daemon=True)
    _laptop_cam_thread.start()
    log_laptop.info("🎥 Camera Laptop started by %s", request.remote_addr)
    _log_event("INFO", "LAPTOP_CAM", "Camera Laptop khởi động")
    return jsonify({"ok": True, "status": "started"})


@app.post("/api/laptop_camera/stop")
def api_laptop_stop():
    global _laptop_frame
    auth = request.headers.get("Authorization", "")
    tok  = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    _laptop_cam_stop.set()
    with _laptop_frame_lock:
        _laptop_frame = None
    log_laptop.info("🛑 Camera Laptop stopped by %s", request.remote_addr)
    _log_event("INFO", "LAPTOP_CAM", "Camera Laptop dừng")
    return jsonify({"ok": True, "status": "stopped"})


@app.get("/api/laptop_camera/status")
def api_laptop_status():
    auth = request.headers.get("Authorization", "")
    tok  = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    with state_lock:
        ctx = dict(context_state)
    ctx_ok, ctx_err = validate_context(ctx)
    ai_status = {}
    try:
        import ai_engine
        ai_status = ai_engine.get_esp32_status()
    except Exception:
        pass
    with _laptop_fps_lock:
        fps = _laptop_fps_value
    return jsonify({
        "ok": True, "active": _laptop_cam_active,
        "frame_ready": _laptop_frame is not None,
        "fps": round(fps, 1),
        "context_ok": ctx_ok, "context_errors": ctx_err,
        "traffic_light": traffic_state["light"],
        "camera_mode": traffic_state["camera"],
        "ai_engine": ai_status,
    })


@app.post("/api/laptop_camera/snapshot")
def api_laptop_snapshot():
    auth = request.headers.get("Authorization", "")
    tok  = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
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
            log_laptop.error("Snapshot save error: %s", e)

    with state_lock:
        cur_light = traffic_state["light"]

    if inject or cur_light == "RED":
        vd = {
            "ts": int(time.time()), "plate": plate,
            "type":           data.get("type", "MOTORBIKE"),
            "speed_kmh":      float(data.get("speed_kmh", 0)),
            "confidence":     float(data.get("confidence", 0.87)),
            "image_b64":      base64.b64encode(frame_bytes).decode() if frame_bytes else "",
            "cam_id":         "LAPTOP_CAM", "roi": "STOP_LINE",
            "vehicles_frame": int(data.get("vehicles_frame", 1)),
        }
        with state_lock:
            traffic_state["light"] = "RED"
        process_violation(vd)

    return jsonify({
        "ok": True, "image_url": image_url, "plate": plate,
        "light": cur_light, "injected": inject or cur_light == "RED",
    })


def _is_ai_engine_running() -> bool:
    """Check if AI engine models are loaded."""
    try:
        import ai_engine
        return ai_engine.get_esp32_status().get("models_ready", False)
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════════════

def _is_valid_token(token: str) -> bool:
    if not token or not token.strip():
        return False
    if token == DASHBOARD_SECRET:
        return True
    if token.startswith("legacy."):
        try:
            decoded = base64.b64decode(token[7:]).decode("utf-8")
            parts   = decoded.split(":")
            if len(parts) >= 3 and parts[0] == _ADMIN_USER:
                age = time.time() - (int(parts[2]) / 1000)
                return 0 <= age < _TOKEN_TTL
        except Exception:
            pass
        return False
    if os.getenv("ALLOW_ANY_TOKEN", "").lower() in ("true", "1", "yes"):
        return True
    return False


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        x_token     = request.headers.get("X-Auth-Token", "")
        tok = auth_header.removeprefix("Bearer ").strip() or x_token.strip()
        if not tok:
            return jsonify({"ok": False, "error": "Unauthorized — no token"}), 401
        if not _is_valid_token(tok):
            return jsonify({"ok": False, "error": "Unauthorized — invalid or expired token"}), 401
        return f(*args, **kwargs)
    return decorated


def require_theme_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        x_token     = request.headers.get("X-Auth-Token", "").strip()
        theme_tok   = request.headers.get("Theme-Token", "").strip()
        main_tok    = auth_header.removeprefix("Bearer ").strip() or x_token
        if main_tok and _is_valid_token(main_tok):
            return f(*args, **kwargs)
        if theme_tok and theme_tok == THEME_TOKEN:
            return f(*args, **kwargs)
        if not main_tok and not theme_tok:
            return jsonify({"ok": False, "error": "Unauthorized", "hint": "POST /api/login"}), 401
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    return decorated


def log_request_timing(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        t0 = time.time()
        result = f(*args, **kwargs)
        ms = (time.time() - t0) * 1000
        if ms > 500:
            log_api.warning("🐢 Slow: %s %s %.1fms", request.method, request.path, ms)
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
                    return jsonify({"ok": False, "error": "Rate limit exceeded"}), 429
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/api/login", methods=["POST"])
@log_request_timing
@rate_limit(max_per_minute=20)
def api_login():
    d = request.get_json(force=True, silent=True) or {}
    u = (d.get("username") or "").strip()
    p = d.get("password") or ""
    if u == _ADMIN_USER and p == _ADMIN_PASS:
        ts_ms = int(time.time() * 1000)
        token = f"legacy.{base64.b64encode(f'{_ADMIN_USER}:{_ADMIN_ROLE}:{ts_ms}'.encode()).decode()}"
        _log_event("INFO", "AUTH", f"Login OK: {u} from {request.remote_addr}")
        return jsonify({"ok": True, "token": token, "role": _ADMIN_ROLE, "ttl": _TOKEN_TTL})
    _log_event("WARN", "AUTH", f"Login FAILED: {u} from {request.remote_addr}")
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401


# ════════════════════════════════════════════════════════════════════════════
# CONTEXT VALIDATOR
# ════════════════════════════════════════════════════════════════════════════

def validate_context(ctx: dict) -> tuple[bool, list[str]]:
    errors = []
    if (s := ctx.get("speed_kmh", 0)) >= 20:
        errors.append(f"🚗 Vận tốc {s:.1f}km/h ≥ 20km/h")
    if (v := ctx.get("vehicles_frame", 0)) > 6:
        errors.append(f"🚦 {v} xe/khung > 6")
    if (w := ctx.get("weather", "SUN")) not in ["SUN", "LIGHT_RAIN", "CLOUDY"]:
        errors.append(f"🌧 Thời tiết '{w}' không hợp lệ")
    if abs((d := ctx.get("distance", 5)) - 5) > 1:
        errors.append(f"📏 Khoảng cách {d}m lệch tối ưu 5m")
    if ctx.get("roi", "STOP_LINE") != "STOP_LINE":
        errors.append("🎯 ROI phải là STOP_LINE")
    if (ci := ctx.get("capture_interval", 0.5)) > 0.5:
        errors.append(f"📸 Tốc độ chụp {ci}s > 0.5s")
    if not set(ctx.get("target_objects", [])) & {"MOTORBIKE", "CAR"}:
        errors.append("🎭 Target objects không hợp lệ")
    return len(errors) == 0, errors


# ════════════════════════════════════════════════════════════════════════════
# DATABASE — SQLite with WAL mode
# ════════════════════════════════════════════════════════════════════════════

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA synchronous=NORMAL")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate TEXT NOT NULL DEFAULT '',
        type TEXT NOT NULL DEFAULT 'UNKNOWN',
        speed_kmh REAL DEFAULT 0,
        light_state TEXT NOT NULL DEFAULT 'RED',
        roi TEXT DEFAULT 'STOP_LINE',
        vehicles_frame INTEGER DEFAULT 0,
        confidence REAL DEFAULT 0,
        image_url TEXT DEFAULT '',
        cam_id TEXT DEFAULT 'CAM_1',
        ts INTEGER NOT NULL,
        date_str TEXT NOT NULL,
        processed INTEGER DEFAULT 0,
        notes TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS device_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        signal REAL, temp REAL, uptime INTEGER,
        status TEXT, ts INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL, source TEXT NOT NULL,
        message TEXT NOT NULL, ts INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS context_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        speed_kmh REAL, vehicles_frame INTEGER,
        weather TEXT, capture_interval REAL,
        fps REAL, context_ok INTEGER, ts INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS theme_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        theme TEXT NOT NULL DEFAULT 'neon-futuristic',
        set_by TEXT DEFAULT 'user',
        auto_selected INTEGER DEFAULT 0,
        ts INTEGER NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_viol_ts    ON violations(ts DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_viol_plate ON violations(plate)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_viol_date  ON violations(date_str)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts  ON system_events(ts DESC)")
    conn.commit()
    conn.close()
    log.info("✅ Database ready: %s", DB_PATH)


init_db()


# ════════════════════════════════════════════════════════════════════════════
# TRAFFIC CYCLE — GREEN(30s) → YELLOW(5s) → RED(30s) → repeat
# ════════════════════════════════════════════════════════════════════════════

TRAFFIC_CYCLE = [
    ("GREEN",  "XANH", "IDLE",   1),
    ("YELLOW", "VÀNG", "WARMUP", 2),
    ("RED",    "ĐỎ",   "ACTIVE", 0),
]
_cycle_idx  = 2   # Start at RED
_cycle_stop = threading.Event()


def _cam_for_light(l: str) -> str:
    return {"GREEN": "IDLE", "YELLOW": "WARMUP", "RED": "ACTIVE"}.get(l, "IDLE")


def _dur(l: str) -> int:
    with state_lock:
        c = traffic_state["cycle"]
        return {"GREEN": c["green_duration"], "YELLOW": c["yellow_duration"], "RED": c["red_duration"]}.get(l, 30)


def _emit_traffic():
    with state_lock:
        p = dict(traffic_state)
    socketio.emit("traffic_state", p)


def _sync_ai_engine_light(light: str):
    """Push light state to ai_engine so it activates/deactivates detection."""
    try:
        import ai_engine
        ai_engine.sync_light_state(light)
        log_ai.debug("Light synced → ai_engine: %s", light)
    except ImportError:
        pass
    except Exception as e:
        log_ai.debug("AI light sync error: %s", e)


# ── PUBLIC API v5.2+ — zero fragile import ──────────────────────────────────

def get_current_light() -> str:
    """
    PUBLIC API — ai_engine reads current traffic light state.
    Thread-safe. Returns "RED" | "YELLOW" | "GREEN".
    Usage: import app; app.get_current_light()
    """
    with state_lock:
        return traffic_state.get("light", "GREEN")


def update_ai_context(vehicles: int, fps: float, **extra) -> None:
    """
    PUBLIC API — ai_engine updates detection context.
    Thread-safe. Auto-validates + emits WebSocket event.
    Usage: import app; app.update_ai_context(vehicles=3, fps=24.5, weather="SUN")

    Args:
        vehicles: vehicle count in frame (clamped to max 6)
        fps:      detection fps (rounded to 1dp)
        **extra:  speed_kmh, weather, distance, capture_interval, roi, target_objects
    """
    with state_lock:
        context_state["vehicles_frame"] = min(int(vehicles), 6)
        context_state["fps"]            = round(float(fps), 1)
        context_state["detection_fps"]  = round(float(fps), 1)
        context_state["updated_at"]     = int(time.time())
        for key, val in extra.items():
            if key in context_state:
                context_state[key] = val
        ok, errs = validate_context(context_state)
        context_state["context_ok"]     = ok
        context_state["context_errors"] = errs
        snapshot = dict(context_state)
    socketio.emit("context_update", snapshot)
    log_ai.debug("Context updated: vehicles=%d fps=%.1f ok=%s", vehicles, fps, ok)


def _traffic_cycle_worker():
    global _cycle_idx
    log.info("🚦 Traffic cycle started (GREEN=%ds YELLOW=%ds RED=%ds)",
             traffic_state["cycle"]["green_duration"],
             traffic_state["cycle"]["yellow_duration"],
             traffic_state["cycle"]["red_duration"])

    while not _cycle_stop.is_set():
        try:
            with state_lock:
                if traffic_state["mode"] == "EMERGENCY":
                    if traffic_state["countdown"] > 0:
                        traffic_state["countdown"] -= 1
                    traffic_state["updated_at"] = int(time.time())
                    _emit_traffic()
                    time.sleep(1)
                    continue

                traffic_state["countdown"] -= 1

                if traffic_state["countdown"] <= 0:
                    _, _, _, ni = TRAFFIC_CYCLE[_cycle_idx]
                    _cycle_idx = ni
                    l, p, cam, _ = TRAFFIC_CYCLE[_cycle_idx]
                    traffic_state.update({
                        "light": l, "phase": p, "camera": cam,
                        "countdown": _dur(l), "updated_at": int(time.time()),
                    })
                    new_light = l
                else:
                    new_light = None
                    traffic_state["updated_at"] = int(time.time())

            _emit_traffic()

            if new_light:
                log.info("🚦 Traffic → %s", new_light)
                _sync_ai_engine_light(new_light)
                with state_lock:
                    ts = dict(traffic_state)
                mqtt_publish(TOPIC_TRAFFIC_STATE, {
                    "light": ts["light"], "countdown": ts["countdown"],
                    "camera": ts["camera"], "ts": int(time.time()),
                })

            time.sleep(1)

        except Exception as e:
            log.error("Traffic cycle error: %s", e)
            time.sleep(1)


def force_light(light: str, mode: str = "EMERGENCY"):
    global _cycle_idx
    idx = {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(light.upper(), 2)
    l, p, cam, _ = TRAFFIC_CYCLE[idx]
    with state_lock:
        _cycle_idx = idx
        traffic_state.update({
            "light": l, "phase": p, "camera": cam, "mode": mode,
            "countdown": _dur(l), "updated_at": int(time.time()),
        })
    _emit_traffic()
    _sync_ai_engine_light(l)
    mqtt_publish(TOPIC_CMD_LIGHT, {"light": l, "mode": mode})
    mqtt_publish(TOPIC_TRAFFIC_STATE, {"light": l, "countdown": _dur(l), "camera": cam, "ts": int(time.time())})
    if mode == "EMERGENCY":
        mqtt_publish(TOPIC_CMD_EMERGENCY, {"active": True, "light": l})


def reset_auto():
    with state_lock:
        traffic_state.update({"mode": "AUTO", "updated_at": int(time.time())})
    _emit_traffic()
    mqtt_publish(TOPIC_CMD_EMERGENCY, {"active": False})


# ════════════════════════════════════════════════════════════════════════════
# THINGSBOARD INTEGRATION
# ════════════════════════════════════════════════════════════════════════════

def _tb_push_telemetry(payload: dict, token: str | None = None):
    tok = token or TB_ACCESS_TOKEN
    if not tok:
        return
    def _send():
        try:
            r = requests.post(f"{TB_HOST}/api/v1/{tok}/telemetry",
                              json=payload, timeout=4,
                              headers={"Content-Type": "application/json"})
            log_tb.debug("TB telemetry: %d", r.status_code)
        except Exception as e:
            log_tb.debug("TB telemetry error: %s", e)
    threading.Thread(target=_send, daemon=True, name="TB-Telem").start()


def _tb_push_attributes(attributes: dict, token: str | None = None):
    tok = token or TB_ACCESS_TOKEN
    if not tok:
        return
    def _send():
        try:
            requests.post(f"{TB_HOST}/api/v1/{tok}/attributes", json=attributes, timeout=4)
        except Exception as e:
            log_tb.debug("TB attributes error: %s", e)
    threading.Thread(target=_send, daemon=True, name="TB-Attrs").start()


def _tb_fetch_attributes(keys: list[str], token: str | None = None) -> dict:
    tok = token or TB_ACCESS_TOKEN
    if not tok:
        return {}
    try:
        r = requests.get(
            f"{TB_HOST}/api/v1/{tok}/attributes?sharedKeys={','.join(keys)}", timeout=3
        )
        if r.status_code == 200:
            return r.json().get("shared", {})
    except Exception:
        pass
    return {}


def _tb_periodic_push():
    while True:
        time.sleep(30)
        if not TB_ACCESS_TOKEN:
            continue
        try:
            with state_lock:
                ts = dict(traffic_state)
                st = dict(system_stats)
            _tb_push_telemetry({
                "light_state":      ts["light"],
                "countdown":        ts["countdown"],
                "violations_today": st["violations_today"],
                "violations_total": st["violations_total"],
                "uptime_s":         int(time.time() - st["start_time"]),
                "current_theme":    _get_current_theme(),
                "server_version":   st["version"],
            })
        except Exception as e:
            log_tb.error("Periodic TB push error: %s", e)


def _tb_sync_theme():
    if not TB_ACCESS_TOKEN:
        return
    try:
        attrs  = _tb_fetch_attributes(["ui_theme", "dashboard_theme"])
        remote = attrs.get("ui_theme") or attrs.get("dashboard_theme")
        if remote and remote in THEME_CONFIG:
            with _theme_lock:
                global _current_theme
                if _current_theme != remote:
                    _current_theme = remote
                    socketio.emit("theme_update", {
                        "theme": remote, "config": THEME_CONFIG[remote], "source": "thingsboard"
                    })
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# THEME MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

def _get_current_theme() -> str:
    with _theme_lock:
        return _current_theme


def _set_theme(theme_name: str, set_by: str = "api", auto: bool = False) -> bool:
    global _current_theme
    if theme_name not in THEME_CONFIG:
        return False
    with _theme_lock:
        old = _current_theme
        _current_theme = theme_name
    if old != theme_name:
        log_theme.info("Theme: %s → %s (by=%s)", old, theme_name, set_by)
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("INSERT INTO theme_preferences(theme,set_by,auto_selected,ts) VALUES(?,?,?,?)",
                         (theme_name, set_by, 1 if auto else 0, int(time.time())))
            conn.commit()
            conn.close()
        except Exception as e:
            log_theme.error("Persist theme error: %s", e)
        config = THEME_CONFIG.get(theme_name, {})
        socketio.emit("theme_update", {
            "theme": theme_name, "config": config,
            "source": set_by, "auto": auto, "ts": int(time.time()),
        })
        mqtt_publish(TOPIC_THEME_UPDATE, {
            "theme": theme_name,
            "primary_color": config.get("colors", {}).get("primary", "#20caff"),
        })
        _tb_push_attributes({"ui_theme": theme_name})
        _log_event("INFO", "THEME", f"Theme: {old} → {theme_name}")
    return True


def _auto_select_theme() -> str:
    with state_lock:
        ctx_ok     = context_state.get("context_ok", True)
        viol_today = system_stats.get("violations_today", 0)
        light      = traffic_state.get("light", "RED")
    if not ctx_ok or viol_today > 10:
        return "neon-alert"
    if light == "GREEN" and ctx_ok:
        return "neon-active"
    return "neon-futuristic"


# ════════════════════════════════════════════════════════════════════════════
# VIOLATION PROCESSOR
# ════════════════════════════════════════════════════════════════════════════

def save_image(b64: str, plate: str, ts: int) -> str:
    if not b64:
        return ""
    try:
        data  = base64.b64decode(b64)
        fname = f"{ts}_{plate.replace(' ','_').replace('/','_')}.jpg"
        (IMAGE_DIR / fname).write_bytes(data)
        return f"/imge/{fname}"
    except Exception as e:
        log.error("save_image: %s", e)
        return ""


def process_violation(payload: dict):
    """
    Process violation from ai_engine or inject API.
    Only saves when light is RED. Emits WebSocket event + ThingsBoard telemetry.

    PUBLIC API — ai_engine calls: import app; app.process_violation(payload)
    """
    ts_v  = payload.get("ts",  int(time.time()))
    plate = payload.get("plate", "").strip().upper()
    vtype = payload.get("type", "UNKNOWN").upper()
    speed = float(payload.get("speed_kmh", 0))
    conf  = float(payload.get("confidence", 0))
    b64   = payload.get("image_b64", "")
    cam   = payload.get("cam_id", "CAM_1")
    roi   = payload.get("roi", "STOP_LINE")
    veh   = int(payload.get("vehicles_frame", 0))

    with state_lock:
        light = traffic_state["light"]

    if light != "RED":
        log_viol.debug("Violation skipped — light=%s (not RED): %s", light, plate)
        return

    date_str  = datetime.fromtimestamp(ts_v, tz=timezone.utc).strftime("%Y-%m-%d")
    image_url = save_image(b64, plate or "UNKNOWN", ts_v)

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        cur  = conn.cursor()
        cur.execute("""INSERT INTO violations
            (plate,type,speed_kmh,light_state,roi,vehicles_frame,confidence,image_url,cam_id,ts,date_str)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (plate, vtype, speed, light, roi, veh, conf, image_url, cam, ts_v, date_str))
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
    except Exception as e:
        log_viol.error("DB insert violation: %s", e)
        return

    with state_lock:
        system_stats["violations_total"]  += 1
        system_stats["violations_today"]  += 1
        system_stats["ai_detections"]     += 1
        context_state["violations_today"]  = system_stats["violations_today"]

    ev = {
        "id": row_id, "plate": plate, "type": vtype, "speed_kmh": speed,
        "light": light, "roi": roi, "vehicles_frame": veh, "confidence": conf,
        "image_url": image_url, "cam_id": cam, "ts": ts_v, "date_str": date_str,
    }
    socketio.emit("new_violation", ev)
    log_viol.warning("🚨 Violation #%d: %s | %s | conf=%.2f | cam=%s", row_id, plate, vtype, conf, cam)
    _log_event("WARN", "AI", f"Vi phạm #{row_id}: {plate} ({vtype}) cam={cam}")

    _tb_push_telemetry({
        "violation_plate":  plate,
        "violation_type":   vtype,
        "violation_speed":  speed,
        "violation_conf":   conf,
        "violations_today": system_stats["violations_today"],
    })

    with state_lock:
        today_count = system_stats["violations_today"]
    if today_count > 10 and _get_current_theme() not in ("neon-alert", "cyber-red"):
        _set_theme("neon-alert", set_by="auto-violation", auto=True)


# ════════════════════════════════════════════════════════════════════════════
# EVENT LOGGER
# ════════════════════════════════════════════════════════════════════════════

def _log_event(level: str, source: str, message: str):
    ts = int(time.time())
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO system_events(level,source,message,ts) VALUES(?,?,?,?)",
                     (level, source, message, ts))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("_log_event DB error: %s", e)
    socketio.emit("system_event", {"level": level, "source": source, "message": message, "ts": ts})


# ════════════════════════════════════════════════════════════════════════════
# MQTT — app-side (ESP32 telemetry + external commands)
# ════════════════════════════════════════════════════════════════════════════

_mqtt_client = None


def mqtt_publish(topic: str, payload):
    if _mqtt_client and _mqtt_client.is_connected():
        data = json.dumps(payload) if isinstance(payload, dict) else payload
        try:
            _mqtt_client.publish(topic, data, qos=1)
        except Exception as e:
            log_mqtt.debug("MQTT publish error: %s", e)


def _on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        log_mqtt.info("✅ MQTT connected %s:%d", MQTT_HOST, MQTT_PORT)
        client.subscribe([
            (TOPIC_ESP32_STATUS,  1),
            (TOPIC_ESP32_FRAME,   0),
            (TOPIC_AI_VIOLATION,  1),
            (TOPIC_AI_CONTEXT,    1),
            (TOPIC_TRAFFIC_STATE, 1),
            (TOPIC_THEME_UPDATE,  1),
        ])
        _log_event("INFO", "MQTT", f"Connected to {MQTT_HOST}")
    else:
        log_mqtt.error("MQTT connect failed rc=%d", rc)


def _on_mqtt_disconnect(client, userdata, rc):
    log_mqtt.warning("MQTT disconnected rc=%d", rc)


def _on_mqtt_message(client, userdata, msg):
    global latest_frame
    with state_lock:
        system_stats["mqtt_messages"] += 1
    try:
        if msg.topic == TOPIC_ESP32_FRAME:
            pl = msg.payload
            frame_bytes = base64.b64decode(pl) if pl[:2] in (b"//", b"/9") else bytes(pl)
            with frame_lock:
                latest_frame = frame_bytes
            with state_lock:
                system_stats["frames_processed"] += 1
                context_state["esp32_connected"]  = True
                context_state["ai_mode"]          = "REAL"
            return

        d = json.loads(msg.payload.decode())

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
                _log_event("INFO", "ESP32", f"Device {dev} online")

        elif msg.topic == TOPIC_AI_VIOLATION:
            process_violation(d)

        elif msg.topic == TOPIC_AI_CONTEXT:
            with state_lock:
                context_state.update({
                    "speed_kmh":        float(d.get("speed_kmh", 0)),
                    "vehicles_frame":   int(d.get("vehicles_frame", 0)),
                    "weather":          d.get("weather", "SUN"),
                    "distance":         float(d.get("distance", 5)),
                    "capture_interval": float(d.get("capture_interval", 0.5)),
                    "roi":              d.get("roi", "STOP_LINE"),
                    "target_objects":   d.get("target_objects", ["MOTORBIKE", "CAR"]),
                    "fps":              float(d.get("fps", 0)),
                    "updated_at":       int(time.time()),
                })
                ok, errs = validate_context(context_state)
                context_state["context_ok"]     = ok
                context_state["context_errors"] = errs
                p = dict(context_state)
            socketio.emit("context_update", p)

        elif msg.topic == TOPIC_TRAFFIC_STATE:
            l = d.get("light", "").upper()
            if l in ("RED", "YELLOW", "GREEN"):
                with state_lock:
                    traffic_state.update({
                        "light": l, "countdown": int(d.get("countdown", 0)),
                        "camera": _cam_for_light(l), "updated_at": int(time.time()),
                    })
                _emit_traffic()
                _sync_ai_engine_light(l)

        elif msg.topic == TOPIC_THEME_UPDATE:
            tn = d.get("theme", "")
            if tn:
                _set_theme(tn, set_by="mqtt-remote", auto=False)

    except Exception as e:
        log_mqtt.error("MQTT msg [%s]: %s", msg.topic, e)


def _init_mqtt():
    global _mqtt_client
    c = mqtt.Client(client_id=f"TrafficAI-v6-{int(time.time())}")
    c.on_connect    = _on_mqtt_connect
    c.on_disconnect = _on_mqtt_disconnect
    c.on_message    = _on_mqtt_message
    try:
        c.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
        c.loop_start()
        _mqtt_client = c
        log_mqtt.info("MQTT client initialized → %s:%d", MQTT_HOST, MQTT_PORT)
    except Exception as e:
        log_mqtt.error("MQTT init failed: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# BACKGROUND WORKERS
# ════════════════════════════════════════════════════════════════════════════

def _device_watchdog():
    while True:
        time.sleep(10)
        now = int(time.time())
        for did, d in devices_state.items():
            try:
                if d["status"] == "ONLINE" and (now - d["last_seen"]) > 30:
                    with state_lock:
                        d["status"] = "OFFLINE"
                    socketio.emit("device_update", {"device_id": did, **d})
                    _log_event("WARN", "WATCHDOG", f"Device {d['name']} went offline")
            except Exception as e:
                log.error("Watchdog error: %s", e)


def _context_snapshot_worker():
    while True:
        time.sleep(60)
        with state_lock:
            ctx = dict(context_state)
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""INSERT INTO context_snapshots
                (speed_kmh,vehicles_frame,weather,capture_interval,fps,context_ok,ts)
                VALUES(?,?,?,?,?,?,?)""",
                (ctx["speed_kmh"], ctx["vehicles_frame"], ctx["weather"],
                 ctx["capture_interval"], ctx["fps"], 1 if ctx["context_ok"] else 0, int(time.time())))
            conn.commit()
            conn.close()
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
                cur.execute("SELECT theme,set_by,ts FROM theme_preferences ORDER BY ts DESC LIMIT 1")
                row = cur.fetchone()
                conn.close()
                was_manual = row and row["set_by"] == "user" and (time.time() - row["ts"]) < 300
            except Exception:
                was_manual = False
            if not was_manual:
                _set_theme(auto_theme, set_by="auto-worker", auto=True)
        except Exception as e:
            log_theme.error("Theme auto worker error: %s", e)


def _ai_engine_status_worker():
    """Monitor AI engine — updates context when ESP32 connects (DEMO → REAL switch)."""
    while True:
        time.sleep(5)
        try:
            import ai_engine
            status = ai_engine.get_esp32_status()
            with state_lock:
                context_state["models_ready"]    = status.get("models_ready", False)
                context_state["esp32_connected"] = status.get("ever_connected", False)
                context_state["ai_mode"] = "REAL" if status.get("ever_connected") else "DEMO"
            socketio.emit("ai_status", {
                **status,
                "demo_mode": not status.get("ever_connected", False),
                "camera_laptop_active": _laptop_cam_active,
            })
        except ImportError:
            with state_lock:
                context_state["ai_mode"] = "NO_AI"
        except Exception as e:
            log_ai.debug("AI status worker error: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# CAMERA LIVE STREAM — ESP32-CAM via MQTT
# ════════════════════════════════════════════════════════════════════════════

def _generate_esp32_placeholder():
    """Waiting-for-ESP32 placeholder frame."""
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    img[:] = (6, 10, 18)
    cv2.putText(img, "CAMERA LIVE", (int(640*0.28), 130),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (15, 50, 120), 2, cv2.LINE_AA)
    cv2.putText(img, "Waiting for ESP32-CAM...", (int(640*0.18), 175),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 100, 180), 2)
    with state_lock:
        light = traffic_state["light"]
    lc = {"RED": (0,0,180), "YELLOW": (0,180,200), "GREEN": (0,180,60)}.get(light, (60,60,60))
    cv2.circle(img, (320, 270), 22, lc, -1)
    cv2.circle(img, (320, 270), 22, (255, 255, 255), 2)
    light_txt = {"RED": "ĐANG ĐỎ", "YELLOW": "ĐANG VÀNG", "GREEN": "ĐANG XANH"}.get(light, light)
    cv2.putText(img, light_txt, (int(640*0.35), 320),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, lc, 1, cv2.LINE_AA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes()


def _gen_esp32_frames():
    """MJPEG generator for Camera Live (/video_feed)."""
    BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    _placeholder = None
    _placeholder_ts = 0.0

    while True:
        with frame_lock:
            frame = latest_frame

        if frame is None:
            now = time.time()
            if _placeholder is None or (now - _placeholder_ts) > 2.0:
                _placeholder = _generate_esp32_placeholder()
                _placeholder_ts = now
            yield BOUNDARY + _placeholder + b"\r\n"
            time.sleep(0.1)
        else:
            yield BOUNDARY + frame + b"\r\n"
            time.sleep(0.033)


@app.get("/video_feed")
def video_feed():
    return Response(_gen_esp32_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


# ════════════════════════════════════════════════════════════════════════════
# REST API
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/bootstrap")
@require_token
@log_request_timing
def api_bootstrap():
    db = get_db()
    cur = db.cursor()
    cur.execute("""SELECT id,plate,type,speed_kmh,light_state,roi,vehicles_frame,
                   confidence,image_url,cam_id,ts,date_str FROM violations ORDER BY ts DESC LIMIT 20""")
    violations = [dict(r) for r in cur.fetchall()]
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM violations WHERE date_str=?", (today,))
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

    ai_info = {}
    try:
        import ai_engine
        ai_info = ai_engine.get_esp32_status()
    except Exception:
        pass

    with _laptop_fps_lock:
        laptop_fps = _laptop_fps_value

    return jsonify({
        "ok": True, "traffic": t, "context": ctx,
        "context_limits": CONTEXT_LIMITS, "camera_optimal": CAMERA_OPTIMAL,
        "devices": devs, "violations": violations, "events": events, "stats": st,
        "laptop_camera_active": _laptop_cam_active,
        "laptop_fps": round(laptop_fps, 1),
        "theme": _get_current_theme(),
        "theme_config": THEME_CONFIG.get(_get_current_theme(), {}),
        "available_themes": list(THEME_CONFIG.keys()),
        "ai_engine": ai_info,
        "server_version": "6.0",
        "demo_mode": not ai_info.get("ever_connected", False),
        "dual_camera": True,  # v6.0: confirms both streams active
    })


@app.get("/api/violations")
@require_token
@log_request_timing
def api_get_violations():
    db = get_db()
    cur = db.cursor()
    pg  = max(1, int(request.args.get("page", 1)))
    pp  = min(100, int(request.args.get("per_page", 20)))
    pq  = request.args.get("plate", "").strip().upper()
    lq  = request.args.get("light", "").upper()
    dq  = request.args.get("date", "")
    tq  = request.args.get("type", "").upper()
    off = (pg - 1) * pp
    w, p = ["1=1"], []
    if pq: w.append("plate LIKE ?"); p.append(f"%{pq}%")
    if lq: w.append("light_state=?"); p.append(lq)
    if dq: w.append("date_str=?");    p.append(dq)
    if tq: w.append("type=?");        p.append(tq)
    wc = " AND ".join(w)
    cur.execute(f"SELECT COUNT(*) FROM violations WHERE {wc}", p)
    total = cur.fetchone()[0]
    cur.execute(f"""SELECT id,plate,type,speed_kmh,light_state,roi,vehicles_frame,
                    confidence,image_url,cam_id,ts,date_str FROM violations
                    WHERE {wc} ORDER BY ts DESC LIMIT ? OFFSET ?""", p + [pp, off])
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({
        "ok": True, "data": rows, "total": total,
        "page": pg, "per_page": pp, "pages": max(1, -(-total // pp)),
    })


@app.delete("/api/violations/<int:vid>")
@require_token
@log_request_timing
def api_delete_violation(vid: int):
    db = get_db()
    db.execute("DELETE FROM violations WHERE id=?", (vid,))
    db.commit()
    _log_event("INFO", "API", f"Violation #{vid} deleted")
    return jsonify({"ok": True})


@app.post("/api/traffic/force")
@require_token
@log_request_timing
def api_force_light():
    d = request.get_json(force=True) or {}
    l = d.get("light", "RED").upper()
    if l not in ("RED", "YELLOW", "GREEN"):
        return jsonify({"ok": False, "error": "Invalid light. Use RED|YELLOW|GREEN"}), 400
    force_light(l, "EMERGENCY")
    return jsonify({"ok": True, "light": l, "mode": "EMERGENCY"})


@app.post("/api/traffic/auto")
@require_token
@log_request_timing
def api_reset_auto():
    reset_auto()
    return jsonify({"ok": True, "mode": "AUTO"})


@app.put("/api/traffic/cycle")
@require_token
@log_request_timing
def api_update_cycle():
    d = request.get_json(force=True) or {}
    with state_lock:
        c = traffic_state["cycle"]
        if "green_duration"  in d: c["green_duration"]  = max(5,  int(d["green_duration"]))
        if "yellow_duration" in d: c["yellow_duration"] = max(3,  int(d["yellow_duration"]))
        if "red_duration"    in d: c["red_duration"]    = max(5,  int(d["red_duration"]))
    return jsonify({"ok": True, "cycle": traffic_state["cycle"]})


@app.get("/api/devices")
@require_token
@log_request_timing
def api_devices():
    with state_lock:
        devs = {k: dict(v) for k, v in devices_state.items()}
    return jsonify({"ok": True, "devices": devs})


@app.get("/api/context")
@require_token
@log_request_timing
def api_context():
    with state_lock:
        ctx = dict(context_state)
    ok, errs = validate_context(ctx)
    return jsonify({
        "ok": True, "context": ctx,
        "limits": CONTEXT_LIMITS, "camera_optimal": CAMERA_OPTIMAL,
        "valid": ok, "errors": errs,
    })


@app.get("/api/events")
@require_token
@log_request_timing
def api_events():
    lv  = request.args.get("level", "")
    lim = min(200, int(request.args.get("limit", 50)))
    db  = get_db()
    cur = db.cursor()
    if lv:
        cur.execute("SELECT * FROM system_events WHERE level=? ORDER BY ts DESC LIMIT ?", (lv.upper(), lim))
    else:
        cur.execute("SELECT * FROM system_events ORDER BY ts DESC LIMIT ?", (lim,))
    return jsonify({"ok": True, "events": [dict(r) for r in cur.fetchall()]})


@app.get("/api/stats")
@require_token
@log_request_timing
def api_stats():
    db  = get_db()
    cur = db.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM violations"); total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM violations WHERE date_str=?", (today,)); td = cur.fetchone()[0]
    cur.execute("""SELECT strftime('%H',datetime(ts,'unixepoch')) hr,COUNT(*) cnt
                   FROM violations WHERE date_str=? GROUP BY hr ORDER BY hr""", (today,))
    by_h = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("""SELECT date_str,COUNT(*) cnt FROM violations WHERE ts>?
                   GROUP BY date_str ORDER BY date_str""", (int(time.time()) - 7*86400,))
    by_d = [{"date": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT type,COUNT(*) cnt FROM violations GROUP BY type")
    by_t = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT AVG(confidence) FROM violations WHERE ts>?", (int(time.time()) - 86400,))
    ac = cur.fetchone()[0] or 0
    with state_lock:
        st = dict(system_stats)
    st["uptime_s"] = int(time.time() - st["start_time"])
    with _laptop_fps_lock:
        laptop_fps = _laptop_fps_value
    return jsonify({
        "ok": True, "total": total, "today": td,
        "by_hour": by_h, "by_day": by_d, "by_type": by_t,
        "avg_conf": round(ac, 3), "system": st,
        "current_theme": _get_current_theme(),
        "laptop_fps": round(laptop_fps, 1),
    })


@app.get("/api/ai/status")
@require_token
@log_request_timing
def api_ai_status():
    info = {}
    try:
        import ai_engine
        info = ai_engine.get_esp32_status()
    except ImportError:
        info = {"available": False, "error": "ai_engine module not found"}
    except Exception as e:
        info = {"available": False, "error": str(e)}

    with state_lock:
        ctx = dict(context_state)
    with _laptop_fps_lock:
        laptop_fps = _laptop_fps_value

    return jsonify({
        "ok": True, "ai_engine": info,
        "demo_mode":    not info.get("ever_connected", False),
        "real_mode":    info.get("ever_connected", False),
        "light":        traffic_state["light"],
        "camera":       traffic_state["camera"],
        "ai_mode":      ctx.get("ai_mode", "DEMO"),
        "models_ready": info.get("models_ready", False),
        # v6.0: dual camera status
        "camera_laptop": {"active": _laptop_cam_active, "fps": round(laptop_fps, 1)},
        "camera_live":   {"source": "ESP32-CAM" if info.get("ever_connected") else "WEBCAM/DEMO"},
    })


@app.post("/api/violations/inject")
@require_token
@log_request_timing
@rate_limit(max_per_minute=30)
def api_inject():
    d = request.get_json(force=True) or {}
    d.setdefault("ts",         int(time.time()))
    d.setdefault("plate",      "51B-12345")
    d.setdefault("type",       "MOTORBIKE")
    d.setdefault("speed_kmh",  14.2)
    d.setdefault("confidence", 0.88)
    d.setdefault("cam_id",     "INJECT_API")
    with state_lock:
        traffic_state["light"] = "RED"
    process_violation(d)
    return jsonify({"ok": True, "message": "Violation injected"})


# ════════════════════════════════════════════════════════════════════════════
# THEME API
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/theme")
@require_theme_token
@log_request_timing
def api_get_theme():
    try:
        _tb_sync_theme()
    except Exception:
        pass
    theme  = _get_current_theme()
    config = THEME_CONFIG.get(theme, {})
    with state_lock:
        ctx_ok = context_state.get("context_ok", True)
    return jsonify({
        "ok": True, "theme": theme, "config": config,
        "available_themes": list(THEME_CONFIG.keys()),
        "context_ok": ctx_ok, "ts": int(time.time()),
    })


@app.post("/api/theme")
@require_token
@log_request_timing
def api_set_theme():
    d  = request.get_json(force=True, silent=True) or {}
    tn = d.get("theme", "").strip()
    if not tn:
        return jsonify({"ok": False, "error": "Missing 'theme' field"}), 400
    if tn not in THEME_CONFIG:
        return jsonify({"ok": False, "error": f"Unknown theme '{tn}'", "valid": list(THEME_CONFIG.keys())}), 400
    if not _set_theme(tn, set_by="user", auto=False):
        return jsonify({"ok": False, "error": "Theme update failed"}), 500
    return jsonify({"ok": True, "theme": tn, "config": THEME_CONFIG[tn], "ts": int(time.time())})


@app.get("/api/theme/list")
@log_request_timing
def api_theme_list():
    return jsonify({"ok": True, "themes": THEME_CONFIG, "current": _get_current_theme()})


@app.get("/api/theme/history")
@require_token
@log_request_timing
def api_theme_history():
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT theme,set_by,auto_selected,ts FROM theme_preferences ORDER BY ts DESC LIMIT 50")
    return jsonify({"ok": True, "history": [dict(r) for r in cur.fetchall()], "current": _get_current_theme()})


# ════════════════════════════════════════════════════════════════════════════
# STATIC FILES
# ════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return send_from_directory(str(FRONTEND_DIR), "main.html")

@app.get("/<path:filename>")
def serve_fe(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)

@app.get("/imge/<path:filename>")
def serve_img(filename):
    return send_from_directory(str(IMAGE_DIR), filename)

@app.get("/api/health")
@log_request_timing
def api_health():
    mqtt_ok = _mqtt_client is not None and _mqtt_client.is_connected()
    ai_info = {}
    try:
        import ai_engine
        ai_info = ai_engine.get_esp32_status()
    except Exception:
        pass
    with _laptop_fps_lock:
        laptop_fps = _laptop_fps_value
    return jsonify({
        "ok": True,
        "server": "AI Traffic Control v6.0",
        "time": int(time.time()),
        "uptime": int(time.time() - system_stats["start_time"]),
        "mqtt": mqtt_ok,
        "theme": _get_current_theme(),
        "version": "6.0",
        "camera_laptop": {"active": _laptop_cam_active, "fps": round(laptop_fps, 1)},
        "camera_live":   {"esp32_connected": ai_info.get("ever_connected", False)},
        "ai_engine": ai_info,
        "demo_mode": not ai_info.get("ever_connected", False),
    })


# ════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ════════════════════════════════════════════════════════════════════════════

@app.errorhandler(400)
def handle_400(e): return jsonify({"ok": False, "error": "Bad request", "detail": str(e)}), 400

@app.errorhandler(401)
def handle_401(e): return jsonify({"ok": False, "error": "Unauthorized"}), 401

@app.errorhandler(403)
def handle_403(e): return jsonify({"ok": False, "error": "Forbidden"}), 403

@app.errorhandler(404)
def handle_404(e): return jsonify({"ok": False, "error": "Not found", "path": request.path}), 404

@app.errorhandler(429)
def handle_429(e): return jsonify({"ok": False, "error": "Too many requests"}), 429

@app.errorhandler(500)
def handle_500(e):
    log.error("500 on %s: %s", request.path, str(e))
    return jsonify({"ok": False, "error": "Internal server error"}), 500


# ════════════════════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS
# ════════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def ws_connect():
    ai_info = {}
    try:
        import ai_engine
        ai_info = ai_engine.get_esp32_status()
    except Exception:
        pass
    with state_lock:
        emit("traffic_state",    dict(traffic_state))
        emit("context_update",   dict(context_state))
        emit("device_list",      {k: dict(v) for k, v in devices_state.items()})
        emit("laptop_cam_status", {
            "active": _laptop_cam_active,
            "fps":    _laptop_fps_value,
        })
        emit("theme_update", {
            "theme":  _get_current_theme(),
            "config": THEME_CONFIG.get(_get_current_theme(), {}),
            "source": "connect",
        })
        emit("ai_status", {
            **ai_info,
            "demo_mode":            not ai_info.get("ever_connected", False),
            "camera_laptop_active": _laptop_cam_active,
            "dual_camera":          True,
        })


@socketio.on("disconnect")
def ws_disconnect():
    log.debug("WebSocket client disconnected")


@socketio.on("cmd_force_light")
def ws_force(data):
    l = (data or {}).get("light", "RED").upper()
    if l in ("RED", "YELLOW", "GREEN"):
        force_light(l)


@socketio.on("cmd_auto")
def ws_auto(_):
    reset_auto()


@socketio.on("ping_server")
def ws_ping(_):
    emit("pong_server", {
        "ts": int(time.time()),
        "theme": _get_current_theme(),
        "laptop_fps": _laptop_fps_value,
    })


@socketio.on("set_theme")
def ws_set_theme(data):
    tn = (data or {}).get("theme", "")
    if tn:
        _set_theme(tn, set_by="ws-client", auto=False)
        emit("theme_update", {
            "theme": tn, "config": THEME_CONFIG.get(tn, {}), "source": "ws-client",
        })


@socketio.on("request_status")
def ws_request_status(_):
    """v6.0: Client can request full status refresh."""
    ai_info = {}
    try:
        import ai_engine
        ai_info = ai_engine.get_esp32_status()
    except Exception:
        pass
    with state_lock:
        emit("full_status", {
            "traffic":        dict(traffic_state),
            "context":        dict(context_state),
            "laptop_cam":     {"active": _laptop_cam_active, "fps": _laptop_fps_value},
            "ai_engine":      ai_info,
            "demo_mode":      not ai_info.get("ever_connected", False),
            "theme":          _get_current_theme(),
        })


# ════════════════════════════════════════════════════════════════════════════
# BOOTSTRAP
# ════════════════════════════════════════════════════════════════════════════

def _bootstrap():
    log.info("=" * 72)
    log.info("🚀 AI Traffic Control v6.0 starting...")
    log.info("   DASHBOARD_SECRET = %s... (len=%d)", DASHBOARD_SECRET[:8], len(DASHBOARD_SECRET))
    log.info("   MQTT: %s:%d", MQTT_HOST, MQTT_PORT)
    log.info("   DB:   %s", DB_PATH)
    log.info("   Camera Laptop → /laptop_feed (VideoCapture(0) by app.py)")
    log.info("   Camera Live   → /video_feed  (ESP32-CAM via ai_engine)")
    log.info("=" * 72)

    # Background workers
    threading.Thread(target=_traffic_cycle_worker,   name="TrafficCycle",   daemon=True).start()
    threading.Thread(target=_device_watchdog,         name="DeviceWatchdog", daemon=True).start()
    threading.Thread(target=_context_snapshot_worker, name="CtxSnapshot",    daemon=True).start()
    threading.Thread(target=_tb_periodic_push,        name="TB-Push",        daemon=True).start()
    threading.Thread(target=_theme_auto_worker,       name="ThemeWorker",    daemon=True).start()
    threading.Thread(target=_ai_engine_status_worker, name="AIStatus",       daemon=True).start()

    # MQTT
    _init_mqtt()

    # ThingsBoard theme sync
    _tb_sync_theme()

    # Restore last theme from DB
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT theme FROM theme_preferences ORDER BY ts DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            _set_theme(row["theme"], set_by="boot-restore", auto=False)
    except Exception:
        pass

    # Auto-start Camera Laptop
    global _laptop_cam_thread
    _laptop_cam_stop.clear()
    _laptop_cam_thread = threading.Thread(target=_laptop_cam_worker, name="LaptopCam", daemon=True)
    _laptop_cam_thread.start()
    log_laptop.info("🎥 Camera Laptop auto-started")

    # Start AI Engine
    try:
        from ai_engine import start_ai
        start_ai(app)
        log_ai.info("🤖 AI Engine started")
        with state_lock:
            current_light = traffic_state["light"]
        _sync_ai_engine_light(current_light)
    except ImportError:
        log_ai.info("ℹ️  ai_engine.py not found — pure demo mode")
        with state_lock:
            context_state["ai_mode"] = "NO_AI"
    except Exception as e:
        log_ai.error("AI Engine start error: %s", e)

    _log_event("INFO", "SYSTEM", "AI Traffic Control v6.0 khởi động thành công")

    log.info("=" * 72)
    log.info("✅ AI Traffic Control v6.0 READY")
    log.info("   🌐 URL:          http://0.0.0.0:5050")
    log.info("   📷 Camera Laptop: http://0.0.0.0:5050/laptop_feed")
    log.info("   📡 Camera Live:   http://0.0.0.0:5050/video_feed")
    log.info("   🔑 Token:         %s", DASHBOARD_SECRET)
    log.info("   🚦 Cycle:         GREEN→YELLOW→RED auto")
    log.info("   🤖 AI detection:  Active when light=RED/YELLOW")
    log.info("   📊 Mode:          DEMO → REAL when ESP32 connects")
    log.info("=" * 72)


if __name__ == "__main__":
    _bootstrap()
    socketio.run(app, host="0.0.0.0", port=5050,
                 debug=False, use_reloader=False, log_output=True)