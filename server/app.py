"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI TRAFFIC CONTROL — BACKEND SERVER v3.0                                   ║
║  Flask + SocketIO + MQTT + SQLite + Laptop Camera Module                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, time, json, sqlite3, threading, logging, base64, re
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests
from flask import Flask, request, jsonify, send_from_directory, Response, g
from flask_socketio import SocketIO, emit

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("TrafficAI")

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

TB_HOST          = os.getenv("TB_HOST", "http://localhost:8080")
TB_ACCESS_TOKEN  = os.getenv("TB_TOKEN", "")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "TRAFFIC_AI_TOKEN")

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
# FIX: Camera không tự mở khi start server
# FIX: Có thể bật lại sau khi tắt (reset stop event + thread)
# FIX: Flip ngang để hiển thị đúng chiều, nhưng OCR dùng frame gốc
# ════════════════════════════════════════════════════════════════
_laptop_cam_active   = False
_laptop_cam_thread   = None
_laptop_frame: bytes | None = None        # Frame đã flip (để hiển thị)
_laptop_frame_raw: bytes | None = None    # Frame gốc chưa flip (để OCR/snapshot)
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
    """
    FIX: Worker thread cho laptop camera.
    - Lưu frame_raw (chưa flip) để dùng cho OCR/snapshot
    - Lưu frame (đã flip ngang) để hiển thị trên web (không bị gương)
    - Thoát sạch khi _laptop_cam_stop được set
    """
    global _laptop_frame, _laptop_frame_raw, _laptop_cam_active
    log.info("🎥 Laptop camera worker starting...")
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  _LAPTOP_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _LAPTOP_H)
        cap.set(cv2.CAP_PROP_FPS, 30)
        log.info("✅ Webcam opened %dx%d", _LAPTOP_W, _LAPTOP_H)
    else:
        cap.release(); cap = None
        log.warning("⚠️  Webcam not found — generating demo frames")

    _laptop_cam_active = True
    fidx = 0

    while not _laptop_cam_stop.is_set():
        if cap:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1); continue
        else:
            frame = np.zeros((_LAPTOP_H, _LAPTOP_W, 3), dtype=np.uint8)
            frame[:] = (10, 18, 28)
            cv2.rectangle(frame, (0, int(_LAPTOP_H*0.44)),
                          (_LAPTOP_W, _LAPTOP_H), (18, 28, 40), -1)
            # Moving demo vehicle
            vx = int((_LAPTOP_W * 0.08) + (fidx * 4) % (_LAPTOP_W * 0.85))
            vy = int(_LAPTOP_H * 0.58)
            cv2.rectangle(frame, (vx-32,vy-20),(vx+32,vy+20),(40,80,180),-1)
            cv2.putText(frame, "51B-12345", (vx-30,vy+8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (240,220,60), 1)
            # 2nd vehicle
            vx2 = int(_LAPTOP_W*0.55 + (fidx*2.5)%(_LAPTOP_W*0.35))
            cv2.rectangle(frame, (vx2-26,vy-26),(vx2+26,vy+26),(160,50,50),-1)
            cv2.putText(frame, "30A-99001",(vx2-24,vy+8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,(240,220,60),1)
            cv2.putText(frame, "DEMO", (int(_LAPTOP_W*0.40), int(_LAPTOP_H*0.38)),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (20,38,60), 4, cv2.LINE_AA)
            fidx += 1

        # Lưu frame gốc (chưa flip) để OCR/snapshot đọc biển số đúng chiều
        frame_with_overlay_raw = _draw_overlay(frame.copy())
        ok_raw, buf_raw = cv2.imencode(".jpg", frame_with_overlay_raw, [cv2.IMWRITE_JPEG_QUALITY, 82])

        # Flip ngang frame để hiển thị (không bị hiệu ứng gương)
        frame_flipped = cv2.flip(frame_with_overlay_raw, 1)
        ok, buf = cv2.imencode(".jpg", frame_flipped, [cv2.IMWRITE_JPEG_QUALITY, 82])

        with _laptop_frame_lock:
            if ok:
                _laptop_frame = buf.tobytes()          # Hiển thị web (đã flip)
            if ok_raw:
                _laptop_frame_raw = buf_raw.tobytes()  # OCR/snapshot (chưa flip)

        time.sleep(0.04)

    # Dọn dẹp khi stop
    if cap:
        cap.release()
    _laptop_cam_active = False
    log.info("🛑 Laptop camera worker stopped")


def _gen_laptop_frames():
    """Stream MJPEG frames đã flip (hiển thị đúng chiều)"""
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


# ── Laptop camera routes ──────────────────────────────────────────

@app.route("/laptop_feed")
def laptop_feed():
    return Response(_gen_laptop_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/laptop_camera/start")
def api_laptop_start():
    """
    FIX: Reset stop event và tạo thread mới mỗi lần start
    Đảm bảo có thể bật lại sau khi đã tắt
    """
    global _laptop_cam_thread, _laptop_frame, _laptop_frame_raw
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok":False,"error":"Unauthorized"}),401

    # Nếu đang chạy rồi thì trả về luôn
    if _laptop_cam_active:
        return jsonify({"ok":True,"status":"already_running"})

    # FIX: Clear stop event TRƯỚC KHI tạo thread mới
    _laptop_cam_stop.clear()

    # FIX: Reset frames cũ
    with _laptop_frame_lock:
        _laptop_frame = None
        _laptop_frame_raw = None

    # FIX: Tạo thread mới mỗi lần (thread cũ đã dead sau khi stop)
    _laptop_cam_thread = threading.Thread(target=_laptop_cam_worker, name="LaptopCam", daemon=True)
    _laptop_cam_thread.start()
    log.info("🎥 Laptop camera started")
    _log_event("INFO","LAPTOP_CAM","Camera laptop khởi động")
    return jsonify({"ok":True,"status":"started"})


@app.post("/api/laptop_camera/stop")
def api_laptop_stop():
    """FIX: Set stop event để thread thoát, clear frames"""
    global _laptop_frame, _laptop_frame_raw
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok":False,"error":"Unauthorized"}),401

    # Set stop event — thread worker sẽ thoát vòng lặp
    _laptop_cam_stop.set()

    # Clear frames để stream hiển thị màn hình "chưa khởi động"
    with _laptop_frame_lock:
        _laptop_frame = None
        _laptop_frame_raw = None

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
    """
    FIX: Dùng _laptop_frame_raw (chưa flip) để lưu ảnh và OCR
    Đảm bảo biển số xe đọc đúng chiều
    """
    auth = request.headers.get("Authorization",""); tok = auth.removeprefix("Bearer ").strip()
    if not _is_valid_token(tok):
        return jsonify({"ok":False,"error":"Unauthorized"}),401

    data   = request.get_json(force=True, silent=True) or {}
    plate  = (data.get("plate") or "SNAP_LAPTOP").strip().upper()
    inject = data.get("inject_violation", False)

    # FIX: Dùng frame_raw (chưa flip) để lưu ảnh — biển số đúng chiều
    with _laptop_frame_lock:
        frame_bytes = _laptop_frame_raw

    image_url = ""
    if frame_bytes:
        ts_now = int(time.time())
        fname  = f"{ts_now}_{plate.replace(' ','_')}_laptop.jpg"
        (IMAGE_DIR / fname).write_bytes(frame_bytes)
        image_url = f"/imge/{fname}"

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
        _log_event("WARN","LAPTOP_CAM",f"Laptop snapshot vi phạm: {plate}")

    return jsonify({"ok":True,"image_url":image_url,"plate":plate,
                    "light":cur_light,"injected": inject or cur_light=="RED"})


# ════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════
_ADMIN_USER = "admin"
_ADMIN_PASS = "admin123"
_ADMIN_ROLE = "superadmin"
_TOKEN_TTL  = 28_800


def _is_valid_token(token: str) -> bool:
    if not token: return False
    if token.startswith("legacy."):
        try:
            parts = base64.b64decode(token[7:]).decode().split(":")
            if len(parts) >= 3 and parts[0] == _ADMIN_USER:
                return 0 <= time.time() - int(parts[2])/1000 < _TOKEN_TTL
        except Exception: pass
        return False
    return token == DASHBOARD_SECRET


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        tok = request.headers.get("Authorization","").removeprefix("Bearer ").strip()
        if not _is_valid_token(tok):
            return jsonify({"ok":False,"error":"Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json(force=True, silent=True) or {}
    u = (d.get("username") or "").strip()
    p = d.get("password") or ""
    if u == _ADMIN_USER and p == _ADMIN_PASS:
        ts_ms = int(time.time()*1000)
        token = f"legacy.{base64.b64encode(f'{_ADMIN_USER}:{_ADMIN_ROLE}:{ts_ms}'.encode()).decode()}"
        _log_event("INFO","AUTH",f"Login OK: {u}")
        return jsonify({"ok":True,"token":token,"role":_ADMIN_ROLE})
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
    if light != "RED": return
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
        log.error("DB insert: %s",e); return
    with state_lock:
        system_stats["violations_total"] += 1; system_stats["violations_today"] += 1
        context_state["violations_today"] = system_stats["violations_today"]
    ev = {"id":row_id,"plate":plate,"type":vtype,"speed_kmh":speed,"light":light,
          "roi":roi,"vehicles_frame":veh,"confidence":conf,"image_url":image_url,
          "cam_id":cam,"ts":ts_v,"date_str":date_str}
    socketio.emit("new_violation",ev)
    log.info("🚨 Violation #%d: %s | %s | %.1fkm/h",row_id,plate,vtype,speed)
    _log_event("WARN","AI",f"Vi phạm #{row_id}: {plate} ({vtype}) @ {speed:.1f}km/h")
    if TB_ACCESS_TOKEN: _push_thingsboard(ev)


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _log_event(level:str, source:str, message:str):
    ts = int(time.time())
    try:
        conn = sqlite3.connect(str(DB_PATH)); conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO system_events(level,source,message,ts) VALUES(?,?,?,?)",
                     (level,source,message,ts)); conn.commit(); conn.close()
    except: pass
    socketio.emit("system_event",{"level":level,"source":source,"message":message,"ts":ts})

def _push_thingsboard(data:dict):
    def _s():
        try: requests.post(f"{TB_HOST}/api/v1/{TB_ACCESS_TOKEN}/telemetry",json=data,timeout=3)
        except: pass
    threading.Thread(target=_s,daemon=True).start()


# ════════════════════════════════════════════════════════════════
# MQTT
# ════════════════════════════════════════════════════════════════
_mqtt_client = None

def mqtt_publish(topic:str, payload):
    if _mqtt_client and _mqtt_client.is_connected():
        _mqtt_client.publish(topic, json.dumps(payload) if isinstance(payload,dict) else payload, qos=1)

def _on_mqtt_connect(client,userdata,flags,rc):
    if rc==0:
        log.info("✅ MQTT connected %s:%d",MQTT_HOST,MQTT_PORT)
        client.subscribe([(TOPIC_ESP32_STATUS,1),(TOPIC_ESP32_FRAME,0),
                          (TOPIC_AI_VIOLATION,1),(TOPIC_AI_CONTEXT,1),(TOPIC_TRAFFIC_STATE,1)])
        _log_event("INFO","MQTT",f"Connected to {MQTT_HOST}")

def _on_mqtt_disconnect(client,userdata,rc):
    log.warning("MQTT disconnected rc=%d",rc)

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
    except Exception as e:
        log.error("MQTT msg [%s]: %s",msg.topic,e)

def _init_mqtt():
    global _mqtt_client
    c = mqtt.Client(client_id=f"TrafficAI-{int(time.time())}")
    c.on_connect=_on_mqtt_connect; c.on_disconnect=_on_mqtt_disconnect; c.on_message=_on_mqtt_message
    try:
        c.connect(MQTT_HOST,MQTT_PORT,MQTT_KEEPALIVE); c.loop_start()
        _mqtt_client = c; log.info("📡 MQTT → %s:%d",MQTT_HOST,MQTT_PORT)
    except Exception as e:
        log.error("MQTT init: %s",e)


# ════════════════════════════════════════════════════════════════
# BACKGROUND WORKERS
# ════════════════════════════════════════════════════════════════
def _device_watchdog():
    while True:
        time.sleep(10)
        now = int(time.time())
        for did,d in devices_state.items():
            if d["status"]=="ONLINE" and (now-d["last_seen"])>30:
                with state_lock: d["status"]="OFFLINE"
                socketio.emit("device_update",{"device_id":did,**d})
                _log_event("WARN","WATCHDOG",f"Device {d['name']} offline")

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
        except: pass


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
            cv2.putText(img,datetime.now().strftime("%H:%M:%S"),(260,220),
                        cv2.FONT_HERSHEY_SIMPLEX,0.7,(100,100,100),1)
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
                    "events":events,"stats":st,"laptop_camera_active":_laptop_cam_active})

@app.get("/api/violations")
@require_token
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
    return jsonify({"ok":True,"data":[dict(r) for r in cur.fetchall()],"total":total,
                    "page":pg,"per_page":pp,"pages":max(1,-(-total//pp))})

@app.delete("/api/violations/<int:vid>")
@require_token
def api_delete_violation(vid:int):
    db=get_db(); db.execute("DELETE FROM violations WHERE id=?",(vid,)); db.commit()
    _log_event("INFO","API",f"Violation #{vid} deleted")
    return jsonify({"ok":True})

@app.post("/api/traffic/force")
@require_token
def api_force_light():
    d=request.get_json(force=True) or {}
    l=d.get("light","RED").upper()
    if l not in ("RED","YELLOW","GREEN"): return jsonify({"ok":False,"error":"Invalid"}),400
    force_light(l,"EMERGENCY"); return jsonify({"ok":True,"light":l})

@app.post("/api/traffic/auto")
@require_token
def api_reset_auto():
    reset_auto(); return jsonify({"ok":True,"mode":"AUTO"})

@app.put("/api/traffic/cycle")
@require_token
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
def api_devices():
    with state_lock: devs={k:dict(v) for k,v in devices_state.items()}
    return jsonify({"ok":True,"devices":devs})

@app.get("/api/context")
@require_token
def api_context():
    with state_lock: ctx=dict(context_state)
    ok,errs=validate_context(ctx)
    return jsonify({"ok":True,"context":ctx,"limits":CONTEXT_LIMITS,
                    "camera_optimal":CAMERA_OPTIMAL,"valid":ok,"errors":errs})

@app.get("/api/events")
@require_token
def api_events():
    lv=request.args.get("level",""); lim=min(200,int(request.args.get("limit",50)))
    db=get_db(); cur=db.cursor()
    if lv: cur.execute("SELECT * FROM system_events WHERE level=? ORDER BY ts DESC LIMIT ?",(lv.upper(),lim))
    else:  cur.execute("SELECT * FROM system_events ORDER BY ts DESC LIMIT ?",(lim,))
    return jsonify({"ok":True,"events":[dict(r) for r in cur.fetchall()]})

@app.get("/api/stats")
@require_token
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
                    "by_type":by_t,"avg_conf":round(ac,3),"system":st})

@app.get("/video_feed")
def video_feed():
    return Response(_generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/health")
def api_health():
    ok = _mqtt_client is not None and _mqtt_client.is_connected()
    return jsonify({"ok":True,"server":"AI Traffic Control v3.0",
                    "time":int(time.time()),"mqtt":ok,
                    "uptime":int(time.time()-system_stats["start_time"]),
                    "laptop_cam":_laptop_cam_active})

@app.post("/api/violations/inject")
@require_token
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
# WEBSOCKET
# ════════════════════════════════════════════════════════════════
@socketio.on("connect")
def ws_connect():
    with state_lock:
        emit("traffic_state",dict(traffic_state))
        emit("context_update",dict(context_state))
        emit("device_list",{k:dict(v) for k,v in devices_state.items()})
        emit("laptop_cam_status",{"active":_laptop_cam_active})

@socketio.on("disconnect")
def ws_disconnect(): pass

@socketio.on("cmd_force_light")
def ws_force(data):
    l=(data or {}).get("light","RED").upper()
    if l in ("RED","YELLOW","GREEN"): force_light(l)

@socketio.on("cmd_auto")
def ws_auto(_): reset_auto()

@socketio.on("ping_server")
def ws_ping(_): emit("pong_server",{"ts":int(time.time())})


# ════════════════════════════════════════════════════════════════
# BOOTSTRAP
# FIX: Không tự động mở camera laptop khi start server
# Camera chỉ mở khi user nhấn nút "Bật Camera" trên web
# ════════════════════════════════════════════════════════════════
def _bootstrap():
    log.info("🚀 AI Traffic Control v3.0")
    # FIX: Đặt stop event ngay từ đầu để camera KHÔNG tự mở
    _laptop_cam_stop.set()
    log.info("📷 Laptop camera: standby (will open when user clicks Bật Camera)")

    threading.Thread(target=_traffic_cycle_worker,  name="TrafficCycle",  daemon=True).start()
    threading.Thread(target=_device_watchdog,        name="DeviceWatchdog",daemon=True).start()
    threading.Thread(target=_context_snapshot_worker,name="CtxSnapshot",  daemon=True).start()
    _init_mqtt()
    try:
        from ai_engine import start_ai; start_ai(app); log.info("🤖 AI engine OK")
    except ImportError: log.info("ℹ️  No ai_engine — demo mode")
    except Exception as e: log.error("AI: %s",e)
    _log_event("INFO","SYSTEM","AI Traffic Control v3.0 khởi động")
    log.info("✅ Ready — port 5050")

if __name__=="__main__":
    _bootstrap()
    socketio.run(app,host="0.0.0.0",port=5050,debug=False,use_reloader=False,log_output=True)