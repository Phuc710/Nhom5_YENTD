# server/app.py
from __future__ import annotations
import os
import json
import time
import sqlite3
import base64
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import paho.mqtt.client as mqtt

# --- CẤU HÌNH ĐƯỜNG DẪN ---
BASE = Path(__file__).resolve().parent             # .../server
DEV = (BASE.parent / "DEVELOPER").resolve()        # .../DEVELOPER
DB_PATH = BASE / "tva.db"

print(f"--- SERVER STARTING ---")
print(f"Server Folder: {BASE}")
print(f"Frontend Folder: {DEV}")

# Load env
load_dotenv(BASE / "config.env")

SECRET = os.getenv("SECRET_KEY", "traffic-ai-enterprise")
APP_PORT = int(os.getenv("PORT", "5051"))
MQTT_ENABLE = True
MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_TOPIC_VIOLATION = os.getenv("MQTT_TOPIC_VIOLATION", "traffic/iot/violation")

app = Flask(__name__)
CORS(app)
serializer = URLSafeTimedSerializer(SECRET)

# --- RUNTIME STATE ---
RUNTIME: Dict[str, Any] = {
    "traffic": {"light": "RED", "countdown": 30, "override": False},
    "clients": [],
}

# --- DATABASE ---
def db_init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS violations (id INTEGER PRIMARY KEY, plate TEXT, speed_kmh REAL, light TEXT, roi TEXT, image_url TEXT, ts INTEGER, vehicle_type TEXT, note TEXT)")
    
    # Tạo user admin mặc định nếu chưa có
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        conn.execute("INSERT INTO users (username, password) VALUES ('admin', 'admin')")
        print("Default user created: admin / admin")
    
    conn.commit()
    conn.close()

db_init()

# --- ROUTES ---
@app.get("/")
def login_page():
    # Kiểm tra xem file có tồn tại không để báo lỗi rõ ràng
    if not (DEV / "login.html").exists():
        return f"Lỗi: Không tìm thấy file login.html tại {DEV}. Hãy kiểm tra lại thư mục DEVELOPER.", 404
    return send_from_directory(DEV, "login.html")

@app.get("/<path:p>")
def serve_assets(p):
    return send_from_directory(DEV, p)

# API Login
@app.post("/api/login")
def api_login():
    data = request.json or {}
    if data.get("username") == "admin" and data.get("password") == "admin":
        token = serializer.dumps({"u": "admin"})
        return jsonify(ok=True, token=token)
    return jsonify(ok=False, error="Sai mật khẩu"), 401

# API Bootstrap (Lấy dữ liệu ban đầu)
@app.get("/api/bootstrap")
def api_bootstrap():
    # Lấy 10 vi phạm mới nhất từ DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM violations ORDER BY ts DESC LIMIT 10").fetchall()
    conn.close()
    
    violations = [dict(r) for r in rows]
    return jsonify(ok=True, traffic=RUNTIME["traffic"], violations=violations)

# API SSE (Realtime)
@app.get("/api/events")
def sse_events():
    def stream():
        q = []
        RUNTIME["clients"].append(q)
        try:
            while True:
                if q:
                    event, payload = q.pop(0)
                    yield f"event: {event}\n"
                    yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(0.1)
                # Keep alive
                yield ": ping\n\n"
        except GeneratorExit:
            RUNTIME["clients"].remove(q)

    return Response(stream(), mimetype="text/event-stream")

# API Tạo Vi Phạm Giả (Test)
@app.post("/api/violation/test")
def create_test_violation():
    vio = {
        "plate": "59-GDU.9999",
        "vehicle_type": "Xe máy",
        "speed_kmh": 45,
        "light": RUNTIME["traffic"]["light"],
        "roi": "Vạch dừng",
        "image_url": "/imge/admin.jpg",
        "ts": int(time.time()),
        "note": "Test click from Web"
    }
    
    # Lưu DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO violations (plate, vehicle_type, speed_kmh, light, roi, image_url, ts, note) VALUES (?,?,?,?,?,?,?,?)",
                 (vio['plate'], vio['vehicle_type'], vio['speed_kmh'], vio['light'], vio['roi'], vio['image_url'], vio['ts'], vio['note']))
    conn.commit()
    conn.close()

    # Bắn realtime ra web
    for q in RUNTIME["clients"]:
        q.append(("violation", vio))
        
    return jsonify(ok=True)

# --- MQTT WORKER ---
def mqtt_worker():
    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            print(f"[MQTT] Nhận vi phạm: {data.get('plate')}")
            # Đẩy ra web
            for q in RUNTIME["clients"]:
                q.append(("violation", data))
            # Lưu DB (Simplified)
            # ... (Code lưu DB tương tự API test)
        except Exception as e:
            print(f"MQTT Error: {e}")

    client = mqtt.Client()
    try:
        client.connect(MQTT_HOST, 1883, 60)
        client.subscribe(MQTT_TOPIC_VIOLATION)
        client.loop_forever()
    except Exception as e:
        print(f"Không thể kết nối MQTT: {e}")

threading.Thread(target=mqtt_worker, daemon=True).start()

if __name__ == "__main__":
    print(f"Server chạy tại: http://localhost:{APP_PORT}")
    app.run(host="0.0.0.0", port=APP_PORT, debug=True, use_reloader=False)