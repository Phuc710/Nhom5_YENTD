"""
╔══════════════════════════════════════════════════════════════════════════════
║  VIRTUAL ESP32 CLUSTER v6.0 — PRODUCTION HARDWARE REPLACEMENT              ║
║  Laptop ASUS TUF GAMING A15 → 100% thay the ESP32-CAM + ESP32 Main        ║
║                                                                              ║
║  CHAY SONG SONG Voi app.py (2 terminal rieng):                             ║
║    Terminal 1:  python server/app.py                                        ║
║    Terminal 2:  python virtual_esp32_cluster.py                              ║
║                                                                              ║
║  ARCHITECTURE:                                                               ║
║  Laptop → MQTT broker.hivemq.com → app.py + ai_engine.py                 ║
║                                                                              ║
║  TOPICS 100% KHOP app.py v3.2:                                              ║
║    PUBLISH: traffic/esp32/frame    → ai_engine._get_frame() → YOLO        ║
║             traffic/esp32/status   → devices_state → Dashboard ONLINE     ║
║             traffic/ai/context     → context_state (GH1-GH7)              ║
║             traffic/ai/violation   → process_violation() → DB + WebSocket ║
║    SUBSCRIBE: traffic/light/state  ← _traffic_cycle_worker() 1s/tick       ║
║               traffic/cmd/light    ← force_light()                         ║
║               traffic/cmd/emergency← Button khan cap                       ║
║                                                                              ║
║  7 GIOI HAN NGU CANH TOI UU ESP32-CAM (app.py CONTEXT_LIMITS):             ║
║    GH1 Van toc        < 20 km/h (tranh nhoe anh OV5640)                    ║
║    GH2 So xe          ≤ 6 phuong tien/khung hinh                           ║
║    GH3 Thoi tiet      SUN / LIGHT_RAIN / CLOUDY (khong lam ban dem)        ║
║    GH4 Khoang cach    5m tu camera den vach dung                            ║
║    GH5 Vung quet      STOP_LINE (ROI tai vach dung)                        ║
║    GH6 Toc do chup    500ms — CHI khi den DO                              ║
║    GH7 Doi tuong      MOTORBIKE + CAR (YOLO class 3 + 2)                  ║
║                                                                              ║
║  CAMERA FIRMWARE CONFIG (camera_config_t C++ tren ESP32-CAM OV5640):       ║
║    frame_size    FRAMESIZE_XGA (1024x768)                                  ║
║    jpeg_quality  8  (OCR-optimal: do nhat → encode nhanh, it nhoe)        ║
║    fb_count      2  (double frame buffer → stream muot)                   ║
║    ae_level      -2 (bu do sang, tranh que sang)                           ║
║    gainceiling   GAINCEILING_4X                                             ║
║    contrast      1  sharpness 2  denoise 1                                 ║
║    xclk_freq_hz  20_000_000 (20MHz — max on dinh)                        ║
║    grab_mode     CAMERA_GRAB_LATEST                                        ║
║    fb_location   CAMERA_FB_IN_PSRAM                                        ║
║                                                                              ║
║  THINGSBOARD TELEMETRY (device camera_AI):                                  ║
║    Telemetry: upload_ok, last_http_code, latency_ms, Wifi_Status           ║
║    Client:    fw_version, camera_id, Model, location                       ║
║    Server:    active, resolution, jpeg_quality, pixel_format               ║
║                                                                              ║
║  THIET BI MO PHONG (khop 100% devices_state trong app.py):                 ║
║    esp32_cam_1  ESP32-CAM #1  192.168.1.101  Camera giam sat chinh         ║
║    esp32_cam_2  ESP32-CAM #2  192.168.1.102  Camera du phong               ║
║    esp32_cam_3  ESP32-CAM #3  192.168.1.103  Camera goc rong               ║
║    esp32_main   ESP32 Main    192.168.1.110  Controller den giao thong     ║
║    esp32_led    LED 7 Doan    192.168.1.111  Hien thi dem nguoc            ║
║                                                                              ║
║  PIPELINE AI THUC TE:                                                       ║
║    Frame JPEG XGA → MQTT → ai_engine nhAN → YOLOv8n detect              ║
║    YOLO bbox trong ROI → crop bien so → EasyOCR → process_violation      ║
║    Vi pham → SQLite DB → SocketIO emit → Dashboard hien thi real-time    ║
╒═════════════════════════════════════════════════════════════════════════════╝
"""

import base64
import json
import logging
import math
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    import paho.mqtt.client as mqtt
    _MQTT_API_V2 = hasattr(mqtt, "CallbackAPIVersion")
except ImportError:
    print("ERROR: pip install paho-mqtt")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════
# LOGGING — format giong app.py
# ════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("VirtualESP32")

# ════════════════════════════════════════════════════════════════════════════
# DIRECT MODE (no external broker) — wired by server/app.py
# ════════════════════════════════════════════════════════════════════════════
_DIRECT_ENABLED = False
_DIRECT_INJECT = None               # inject_func(topic:str, payload_bytes:bytes) -> None
_DIRECT_SUBSCRIBE_LOCAL = None      # subscribe_local_func(callback(topic,payload_bytes))
_DIRECT_GET_TRAFFIC_STATE = None    # get_traffic_state_func() -> dict


def enable_direct_mode(inject_func, subscribe_local_func=None, get_traffic_state_func=None):
    """
    Enable in-process mode so the cluster runs without Mosquitto.
    Called by server/app.py when localhost:1883 is unavailable.
    """
    global _DIRECT_ENABLED, _DIRECT_INJECT, _DIRECT_SUBSCRIBE_LOCAL, _DIRECT_GET_TRAFFIC_STATE
    _DIRECT_ENABLED = True
    _DIRECT_INJECT = inject_func
    _DIRECT_SUBSCRIBE_LOCAL = subscribe_local_func
    _DIRECT_GET_TRAFFIC_STATE = get_traffic_state_func


class _DirectMQTTClient:
    """Minimal MQTT-like client for direct-mode (no sockets)."""
    def __init__(self, client_id: str):
        self._id = client_id
        self._connected = False
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

    def is_connected(self):
        return self._connected

    def connect(self, host=None, port=None, keepalive=None):
        self._connected = True
        if callable(self.on_connect):
            try:
                self.on_connect(self, None, None, 0)
            except TypeError:
                try:
                    self.on_connect(self, None, None, 0, None)
                except Exception:
                    pass

    def loop_start(self):  # noqa: D401
        return

    def loop_stop(self):
        return

    def disconnect(self):
        self._connected = False
        if callable(self.on_disconnect):
            try:
                self.on_disconnect(self, None, 0)
            except TypeError:
                try:
                    self.on_disconnect(self, None, None, 0, None)
                except Exception:
                    pass

    def subscribe(self, topics):
        # No-op: app.py will push command/state messages via local bus injection.
        return

    def publish(self, topic, payload, qos=0):
        if not _DIRECT_INJECT:
            return
        if isinstance(payload, (dict, list)):
            payload_bytes = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode("utf-8")
        _DIRECT_INJECT(topic, payload_bytes)

    def inject_message(self, topic: str, payload_bytes: bytes):
        """Receive app->cluster messages (cmd/light/emergency/traffic state) via local bus."""
        if not callable(self.on_message):
            return

        class _Msg:
            def __init__(self, t, p):
                self.topic = t
                self.payload = p

        try:
            self.on_message(self, None, _Msg(topic, payload_bytes))
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS — copy verbatim tu app.py
# ════════════════════════════════════════════════════════════════════════════
MQTT_HOST           = "localhost"
MQTT_PORT           = 1883
MQTT_KEEPALIVE      = 60

TOPIC_ESP32_STATUS  = "traffic/esp32/status"    # PUBLISH: heartbeat thiet bi
TOPIC_ESP32_FRAME   = "traffic/esp32/frame"     # PUBLISH: raw JPEG bytes
TOPIC_AI_VIOLATION  = "traffic/ai/violation"    # PUBLISH: vi pham vuot den do
TOPIC_AI_CONTEXT    = "traffic/ai/context"      # PUBLISH: 7 gioi han ngu canh
TOPIC_TRAFFIC_STATE = "traffic/light/state"     # SUBSCRIBE: trang thai den tu server
TOPIC_CMD_LIGHT     = "traffic/cmd/light"       # SUBSCRIBE: lenh den tu dashboard
TOPIC_CMD_EMERGENCY = "traffic/cmd/emergency"   # SUBSCRIBE: khan cap

# Camera OV5640 firmware config — khop CAMERA_OPTIMAL trong app.py
CAM_CFG = {
    "frame_size":    "FRAMESIZE_XGA",
    "jpeg_quality":  8,
    "fb_count":      2,
    "ae_level":      -2,
    "gainceiling":   "GAINCEILING_4X",
    "contrast":      1,
    "sharpness":     2,
    "denoise":       1,
    "xclk_freq_hz":  20_000_000,
    "pixel_format":  "PIXFORMAT_JPEG",
    "grab_mode":     "CAMERA_GRAB_LATEST",
    "fb_location":   "CAMERA_FB_IN_PSRAM",
}
CAM_W, CAM_H   = 1024, 768      # FRAMESIZE_XGA
CAM_FPS        = 15              # ESP32-CAM XGA thuc te ~15 FPS
CAPTURE_IV_S   = 0.5             # GH6: 500ms capture interval khi den do
WATCHDOG_TTL   = 30              # app.py watchdog: offline neu khong gui status 30s

# ════════════════════════════════════════════════════════════════════════════
# DEVICE REGISTRY — khop 100% devices_state trong app.py
# ════════════════════════════════════════════════════════════════════════════
DEVICES = {
    "esp32_cam_1": {
        "name": "ESP32-CAM #1",
        "ip":   "192.168.1.101",
        "fw":   "v6.1-XGA-OCR-Production",
        "model": "AI-Traffic-Camera-OV5640",
        "camera_id": "CAM_001",
        "location": {"lat": 10.7769, "lng": 106.7009},
        "role": "camera",
        "primary": True,   # cam_1 la primary: publish context + violation chinh
    },
    "esp32_cam_2": {
        "name": "ESP32-CAM #2",
        "ip":   "192.168.1.102",
        "fw":   "v6.1-XGA-OCR-Production",
        "model": "AI-Traffic-Camera-OV5640",
        "camera_id": "CAM_002",
        "location": {"lat": 10.7775, "lng": 106.7015},
        "role": "camera",
        "primary": False,
    },
    "esp32_cam_3": {
        "name": "ESP32-CAM #3",
        "ip":   "192.168.1.103",
        "fw":   "v6.1-XGA-OCR-Production",
        "model": "AI-Traffic-Camera-OV5640",
        "camera_id": "CAM_003",
        "location": {"lat": 10.7780, "lng": 106.7020},
        "role": "camera",
        "primary": False,
    },
    "esp32_main": {
        "name": "ESP32 Main",
        "ip":   "192.168.1.110",
        "fw":   "v4.2-TrafficController",
        "model": "TrafficLight-Controller-Dual",
        "camera_id": "MAIN_CTRL",
        "role": "controller",
        "primary": False,
    },
    "esp32_led": {
        "name": "LED 7 Doan",
        "ip":   "192.168.1.111",
        "fw":   "v2.0-LED7SEG-Countdown",
        "model": "LED-7Segment-Display",
        "camera_id": "LED_DISP",
        "role": "display",
        "primary": False,
    },
}

# ════════════════════════════════════════════════════════════════════════════
# BIEN SO VIET NAM THUC TE — Pool 40 bien so
# ════════════════════════════════════════════════════════════════════════════
VN_PLATES = [
    # TP. Ho Chi Minh (51, 59)
    "51B-12345", "59D-67890", "51C-11222", "59F-33445", "51G-70601",
    "51A-00001", "59B-00002", "51H-00003", "59K-00004", "51L-00005",
    "59A-98765", "51D-54321", "59G-11111", "51K-22222", "59H-33333",
    # Ha Noi (29, 30)
    "29A-12345", "30B-67890", "29C-11222", "30D-55667", "29E-99001",
    "30F-33445", "29G-70601", "30H-88888", "29K-24680", "30L-13579",
    "30A-00010", "29B-00020", "30C-00030", "29D-00040", "30E-00050",
    # Cac tinh khac
    "43A-11111", "92B-22222", "36C-33333", "71D-44444", "47E-55555",
    "75F-66666", "77G-77777", "61H-99999", "65K-12321", "86L-45654",
]

# Types khop GH7 va TARGET_CLASSES trong ai_engine
VEH_TYPES    = ["MOTORBIKE", "CAR"]
WEATHER_POOL = ["SUN", "SUN", "SUN", "SUN", "CLOUDY", "CLOUDY", "LIGHT_RAIN"]

# Mau xe thuc te
CAR_COLORS = [
    (45, 88, 195), (28, 28, 165), (165, 32, 32), (32, 130, 32),
    (205, 205, 205), (20, 20, 20), (198, 142, 28), (95, 45, 165),
    (0, 155, 155), (145, 85, 35), (60, 60, 60), (195, 195, 50),
]


# ════════════════════════════════════════════════════════════════════════════
# TRAFFIC STATE SYNC — nhan tu server, countdown local fallback
# ════════════════════════════════════════════════════════════════════════════
class TrafficStateSync:
    """
    Sync trang thai den giao thong tu server qua MQTT.
    Fallback: tu countdown local neu server cham.
    Giong cach ESP32 thuc doc lenh tu MQTT va update LED 7 doan.
    """
    DURATIONS = {"RED": 30, "YELLOW": 5, "GREEN": 30}
    SEQ       = {"RED": "GREEN", "GREEN": "YELLOW", "YELLOW": "RED"}

    def __init__(self):
        self._lock      = threading.RLock()
        self.light      = "RED"
        self.countdown  = 30
        self.mode       = "AUTO"
        self._updated   = time.time()
        # Stats
        self.sync_count = 0
        self.tick_count = 0

    def server_update(self, light: str, countdown: int, mode: str = "AUTO"):
        """Nhan update tu server — priority cao nhat."""
        with self._lock:
            changed    = self.light != light
            prev       = self.light
            self.light = light
            self.countdown = countdown
            self.mode  = mode
            self._updated  = time.time()
            self.sync_count += 1
        if changed:
            icons = {"RED": "[DO]", "YELLOW": "[VANG]", "GREEN": "[XANH]"}
            log.info("%s Light changed: %s -> %s  countdown=%ds  mode=%s  (server sync #%d)",
                     icons.get(light, "[?]"), prev, light, countdown, mode, self.sync_count)

    def local_tick(self):
        """Goi moi 1 giay tu countdown_worker — fallback khi mat tin hieu server."""
        with self._lock:
            if self.countdown > 0:
                self.countdown -= 1
            else:
                # Tu dong chuyen pha (mô phong _traffic_cycle_worker cua app.py)
                self.light     = self.SEQ.get(self.light, "RED")
                self.countdown = self.DURATIONS.get(self.light, 30)
            self.tick_count += 1

    def get(self):
        with self._lock:
            return self.light, self.countdown, self.mode


_traffic = TrafficStateSync()
_running = threading.Event()
_running.set()


# ════════════════════════════════════════════════════════════════════════════
# SCENE RENDERER — Render canh giao thong thuc te XGA 1024x768
# ════════════════════════════════════════════════════════════════════════════
class SceneRenderer:
    """
    Render khung hinh giao thong XGA (1024x768) giong output camera OV5640.
    - Duong pho 3 lan xe
    - Xe oto + xe may di chuyen thuc te
    - Bien so xe in tren xe (de OCR doc)
    - Den giao thong 3 bong RGB
    - ROI STOP LINE (ai_engine.py: ROI_RATIO_TOP=0.60 ~ ROI_RATIO_BOTTOM=0.90)
    - HUD: timestamp, trang thai den, thong tin camera
    - Hieu ung thoi tiet: mua nhe, may mu
    - JPEG quality=8 (khop CAM_CFG, OCR-optimal)
    """

    # Vung ROI khop voi ai_engine.py constants
    ROI_TOP    = 0.60
    ROI_BOTTOM = 0.90
    ROI_LEFT   = 0.04
    ROI_RIGHT  = 0.96

    def __init__(self, cam_id: str):
        self.cam_id   = cam_id
        self.fidx     = 0
        self._weather = random.choice(WEATHER_POOL)
        self._wx_ts   = time.time()
        self._vehicles = self._spawn_vehicles(random.randint(3, 6))
        self._noise_seed = random.randint(0, 9999)

    # ── Vehicle pool ──────────────────────────────────────────────────────
    def _spawn_vehicles(self, count: int) -> list:
        vehicles = []
        lanes = list(range(3)) * 4
        random.shuffle(lanes)
        for i in range(min(count, 6)):   # GH2: max 6
            vtype = random.choice(VEH_TYPES)
            lane  = lanes[i % len(lanes)]
            w = random.randint(78, 118) if vtype == "CAR" else random.randint(42, 62)
            vehicles.append({
                "id":     i,
                "type":   vtype,
                "plate":  random.choice(VN_PLATES),
                "color":  random.choice(CAR_COLORS),
                "w":      w,
                "lane":   lane,
                "x":      random.randint(60, CAM_W - 180),
                "spd":    random.uniform(1.6, 3.8),   # px/frame ~ 8-19 km/h (GH1)
                "stopped": False,
            })
        return vehicles

    def _lane_y(self, lane: int) -> int:
        """
        Y coordinate cua tam xe tren moi lan.
        ROI cua ai_engine.py: ROI_TOP=0.60 den ROI_BOTTOM=0.90.
        Xe can phai nam trong vung [ROI_TOP*H .. ROI_BOTTOM*H] de YOLO detect.
        """
        roi_mid = int(CAM_H * (self.ROI_TOP + self.ROI_BOTTOM) / 2)  # ~540px
        offsets = [roi_mid + 50, roi_mid, roi_mid - 50]
        return offsets[lane % 3]

    def _get_weather(self) -> str:
        # Thoi tiet thay doi moi 5 phut (thuc te)
        if time.time() - self._wx_ts > 300:
            self._weather = random.choice(WEATHER_POOL)
            self._wx_ts   = time.time()
            log.info("[%s] Thoi tiet thay doi: %s", self.cam_id, self._weather)
        return self._weather

    def get_weather(self) -> str:
        """FIX v5.1: Public alias cho _get_weather() — CameraNode._context_payload() gọi hàm này."""
        return self._get_weather()

    # ── Vehicle physics ───────────────────────────────────────────────────
    def _update_vehicles(self, light: str, n_active: int):
        """Cap nhat vi tri xe theo trang thai den va cac rang buoc GH1-GH2."""
        stop_y = int(CAM_H * self.ROI_TOP) + 5   # Vach dung ~ ROI_TOP
        active = self._vehicles[:min(n_active, 6)]

        for v in active:
            ly = self._lane_y(v["lane"])

            if light == "RED":
                dist_to_stop = ly - stop_y
                if dist_to_stop > 0 and not v["stopped"]:
                    # Xe dang tien den vach, giam toc dan
                    move = min(v["spd"] * 2.5, max(0.5, dist_to_stop * 0.15))
                    v["x"] = int(v["x"] + move * 0.3)
                    if dist_to_stop < 12:
                        v["stopped"] = True
                elif v["stopped"]:
                    # Xe da dung — 4% nguoi vuot den do (vi pham)
                    if random.random() < 0.04:
                        v["stopped"] = False
                        v["x"] = (v["x"] + int(v["spd"])) % (CAM_W - v["w"] - 20)
                else:
                    # Xe phia tren ROI — di chuyen binh thuong
                    v["x"] = (v["x"] + int(v["spd"])) % (CAM_W - v["w"] - 20)
            else:
                # Den xanh / vang: xe di chuyen
                v["stopped"] = False
                speed_mult   = 2.2 if light == "GREEN" else 1.4
                v["x"] = (v["x"] + int(v["spd"] * speed_mult)) % (CAM_W - v["w"] - 20)

    # ── Draw helpers ──────────────────────────────────────────────────────
    def _draw_sky_road(self, img: np.ndarray, weather: str):
        """Ve bau troi va mat duong thuc te."""
        horizon = int(CAM_H * 0.42)
        sky_top = {"SUN": (135, 195, 235), "CLOUDY": (70, 90, 110), "LIGHT_RAIN": (50, 60, 90)
                   }.get(weather, (100, 130, 160))

        # Bau troi gradient
        for y in range(horizon):
            t = y / horizon
            r = int(sky_top[2] + (180 - sky_top[2]) * (1 - t) * 0.3)
            g = int(sky_top[1] + (200 - sky_top[1]) * (1 - t) * 0.2)
            b = int(sky_top[0] + (220 - sky_top[0]) * (1 - t) * 0.1)
            img[y, :] = (max(0, min(255, b)), max(0, min(255, g)), max(0, min(255, r)))

        # Mat duong (asphalt)
        img[horizon:, :] = (40, 45, 50)
        # Viền chân trời
        img[horizon:horizon + 2, :] = (60, 68, 75)

    def _draw_road_markings(self, img: np.ndarray):
        """Vach ke duong, lan xe, vach ngoc soc."""
        h, w = img.shape[:2]
        road_start = int(h * 0.42)

        # 3 lan xe — vach phan cach
        for lx_ratio in [0.33, 0.66]:
            lx = int(w * lx_ratio)
            for dy in range(road_start, h, 45):
                end_y = min(dy + 24, h - 1)
                cv2.line(img, (lx, dy), (lx, end_y), (185, 175, 55), 1)

        # Vach bien duong trai phai
        cv2.line(img, (int(w * 0.02), road_start), (int(w * 0.02), h), (220, 220, 220), 2)
        cv2.line(img, (int(w * 0.98), road_start), (int(w * 0.98), h), (220, 220, 220), 2)

    def _draw_stop_line(self, img: np.ndarray, light: str):
        """
        Ve ROI STOP LINE — vi tri khop chinh xac voi ai_engine.py:
        roi_y1 = int(h * ROI_RATIO_TOP) = int(768 * 0.60) = 460px
        """
        h, w = img.shape[:2]
        roi_y1 = int(h * self.ROI_TOP)
        roi_y2 = int(h * self.ROI_BOTTOM)
        roi_x1 = int(w * self.ROI_LEFT)
        roi_x2 = int(w * self.ROI_RIGHT)

        # Mau vach dung theo trang thai den (khop ai_engine logic)
        line_color = (50, 50, 225) if light == "RED" else (50, 200, 225)
        cv2.line(img, (roi_x1, roi_y1), (roi_x2, roi_y1), line_color, 3)

        # Label vach dung
        cv2.putText(img, "STOP LINE  |  ROI DETECTION ZONE  |  VACH DUNG",
                    (roi_x1 + 8, roi_y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, line_color, 1, cv2.LINE_AA)

        # Vung ROI rectangle (mo)
        roi_overlay = img.copy()
        cv2.rectangle(roi_overlay, (roi_x1, roi_y1), (roi_x2, roi_y2),
                      (30, 30, 160) if light == "RED" else (30, 120, 160), -1)
        cv2.addWeighted(roi_overlay, 0.06, img, 0.94, 0, img)

    def _draw_vehicle(self, img: np.ndarray, v: dict, light: str):
        """
        Ve xe thuc te voi bien so ro rang de OCR co the doc.
        Vi tri xe phai nam TRONG vung ROI de YOLO detect duoc vi pham.
        """
        x  = int(v["x"])
        y  = self._lane_y(v["lane"])
        w  = v["w"]
        c  = v["color"]

        if v["type"] == "CAR":
            # Than xe
            cv2.rectangle(img, (x, y - 42), (x + w, y + 12), c, -1)
            # Kinh xe
            cv2.rectangle(img, (x + 7, y - 37), (x + w - 7, y - 20),
                          (160, 195, 215), -1)
            # Khung kinh
            cv2.rectangle(img, (x + 7, y - 37), (x + w - 7, y - 20),
                          tuple(max(0, c_-30) for c_ in c), 1)
            # Duong vien xe
            cv2.rectangle(img, (x, y - 42), (x + w, y + 12),
                          tuple(max(0, c_-35) for c_ in c), 1)
            # 4 banh xe
            for wx in [x + 14, x + w - 14]:
                cv2.circle(img, (wx, y + 12), 9, (14, 14, 14), -1)
                cv2.circle(img, (wx, y + 12), 5, (45, 45, 45), -1)
            # Den xe (truoc / sau)
            for hx in [x, x + w - 8]:
                cv2.rectangle(img, (hx, y - 10), (hx + 8, y + 2),
                              (220, 220, 100) if hx == x else (200, 60, 60), -1)
            # Bien so xe — de OCR doc (khop _run_ocr trong ai_engine.py)
            plate_x = x + 4
            plate_y = y + 4
            cv2.rectangle(img, (plate_x, plate_y - 14),
                          (plate_x + 70, plate_y + 4), (240, 238, 25), -1)
            cv2.rectangle(img, (plate_x, plate_y - 14),
                          (plate_x + 70, plate_y + 4), (30, 30, 30), 1)
            cv2.putText(img, v["plate"][:9], (plate_x + 2, plate_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (12, 12, 12), 1, cv2.LINE_AA)

        else:  # MOTORBIKE — class 3 trong YOLO (TARGET_CLASSES)
            hw = w // 2
            # Than xe may (oval)
            cv2.ellipse(img, (x + hw, y - 5), (hw, 20), 0, 0, 360, c, -1)
            cv2.ellipse(img, (x + hw, y - 5), (hw, 20), 0, 0, 360,
                        tuple(max(0, c_-30) for c_ in c), 1)
            # Nguoi lai (hinh tron)
            cv2.circle(img, (x + hw, y - 26), 10, (180, 130, 90), -1)
            # 2 banh
            for wx in [x + 9, x + w - 9]:
                cv2.circle(img, (wx, y + 7), 7, (14, 14, 14), -1)
                cv2.circle(img, (wx, y + 7), 3, (45, 45, 45), -1)
            # Bien so xe may nho hon
            plate_x = x + 2
            plate_y = y + 3
            cv2.rectangle(img, (plate_x, plate_y - 12),
                          (plate_x + 56, plate_y + 2), (240, 238, 25), -1)
            cv2.rectangle(img, (plate_x, plate_y - 12),
                          (plate_x + 56, plate_y + 2), (30, 30, 30), 1)
            cv2.putText(img, v["plate"][:8], (plate_x + 2, plate_y - 1),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.26, (12, 12, 12), 1, cv2.LINE_AA)

    def _draw_traffic_light(self, img: np.ndarray, light: str, countdown: int):
        """Ve bo den giao thong goc phai — 3 bong Den/Vang/Xanh."""
        px, py_base = CAM_W - 52, int(CAM_H * 0.08)
        # Cot den
        cv2.rectangle(img, (px - 24, py_base), (px + 24, int(CAM_H * 0.62)),
                      (26, 28, 33), -1)
        cv2.rectangle(img, (px - 24, py_base), (px + 24, int(CAM_H * 0.62)),
                      (45, 48, 55), 1)
        # 3 Bong den
        light_defs = [("RED", (0, 0, 215)), ("YELLOW", (0, 185, 215)), ("GREEN", (0, 195, 65))]
        for i, (lname, lcolor) in enumerate(light_defs):
            cy = py_base + 22 + i * 55
            cv2.circle(img, (px, cy), 21, (12, 13, 16), -1)
            on_color  = lcolor
            off_color = tuple(int(c_ * 0.12) for c_ in lcolor)
            cv2.circle(img, (px, cy), 17, on_color if light == lname else off_color, -1)
            if light == lname:
                # Hao quang khi sang
                for r_extra in [19, 21]:
                    cv2.circle(img, (px, cy), r_extra, on_color, 1)
        # Dem nguoc (khop LED 7 doan thuc te)
        lc = {"RED": (0, 0, 255), "YELLOW": (0, 210, 255), "GREEN": (0, 255, 95)
              }.get(light, (200, 200, 200))
        cv2.putText(img, str(countdown), (px - 14, int(CAM_H * 0.49)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.90, lc, 2, cv2.LINE_AA)

    def _draw_weather_fx(self, img: np.ndarray, weather: str):
        """Hieu ung thoi tiet thuc te."""
        if weather == "LIGHT_RAIN":
            rng = np.random.RandomState((self.fidx + self._noise_seed) % 1000)
            for _ in range(65):
                rx = rng.randint(0, CAM_W)
                ry = rng.randint(0, CAM_H)
                cv2.line(img, (rx, ry), (rx - 1, ry + 10), (82, 102, 138), 1)
            # Giam do sang nhe (troi toi khi mua)
            img[:] = cv2.addWeighted(img, 0.88,
                                     np.full_like(img, (28, 32, 45)), 0.12, 0)
        elif weather == "CLOUDY":
            # May mu — giam do tuong phan
            img[:int(CAM_H * 0.42)] = cv2.addWeighted(
                img[:int(CAM_H * 0.42)], 0.72,
                np.full((int(CAM_H * 0.42), CAM_W, 3), (65, 78, 95), dtype=np.uint8), 0.28, 0)

    def _draw_hud(self, img: np.ndarray, light: str, weather: str,
                  n_veh: int, countdown: int):
        """
        HUD overlay — khop _draw_overlay() trong app.py (laptop camera).
        Thong tin: timestamp, trang thai den, cam mode, weather, vehicle count.
        """
        h, w = img.shape[:2]

        # Top bar (giong app.py _draw_overlay)
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, 34), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.68, img, 0.32, 0, img)

        # Timestamp
        ts_str = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
        cv2.putText(img, "[{}]  {}".format(self.cam_id.upper(), ts_str),
                    (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 228, 255), 1, cv2.LINE_AA)

        # Trang thai den (goc phai top)
        lc = {"RED": (0, 0, 255), "YELLOW": (0, 205, 255), "GREEN": (0, 255, 105)
              }.get(light, (200, 200, 200))
        ln = {"RED": "DO", "YELLOW": "VANG", "GREEN": "XANH"}.get(light, light)
        cv2.putText(img, "DEN: {}  {}s".format(ln, countdown),
                    (w - 200, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, lc, 1, cv2.LINE_AA)

        # Den LED tron trang thai (giong _draw_overlay app.py)
        cv2.circle(img, (w - 22, 44), 12, lc, -1)
        cv2.circle(img, (w - 22, 44), 12, (255, 255, 255), 1)

        # Bottom bar
        overlay2 = img.copy()
        cv2.rectangle(overlay2, (0, h - 32), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay2, 0.68, img, 0.32, 0, img)

        cam_st = "ACTIVE" if light in ("RED", "YELLOW") else "IDLE"
        sc = (0, 205, 75) if cam_st == "ACTIVE" else (68, 68, 68)

        # Trang thai camera + thong so (GH1-GH7)
        cv2.putText(img,
            "CAM:{} | WX:{} | VEH:{}/6 | {}x{} | Q={} | {}fps".format(
                cam_st, weather, n_veh, CAM_W, CAM_H, CAM_CFG["jpeg_quality"], CAM_FPS),
            (8, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, sc, 1, cv2.LINE_AA)

        # Frame index goc phai bottom
        cv2.putText(img, "FRAME #{:07d}".format(self.fidx),
                    (w - 195, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (100, 100, 150), 1, cv2.LINE_AA)

        # YOLO badge khi camera ACTIVE (giong Source badge trong ai_engine.py)
        if cam_st == "ACTIVE":
            cv2.putText(img, "ESP32-CAM LIVE  YOLOv8n + OCR",
                        (8, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 200, 80), 1, cv2.LINE_AA)

    # ── Main render ───────────────────────────────────────────────────────
    def render(self, n_vehicles: int) -> bytes:
        """
        Render 1 frame hoan chinh XGA 1024x768 -> JPEG bytes.
        Encode voi jpeg_quality=8 (khop CAM_CFG, OCR-optimal).
        """
        light, countdown, mode = _traffic.get()
        weather = self._get_weather()

        img = np.zeros((CAM_H, CAM_W, 3), dtype=np.uint8)

        # Layer 1: Nen bau troi + mat duong
        self._draw_sky_road(img, weather)

        # Layer 2: Vach ke duong
        self._draw_road_markings(img)

        # Layer 3: Cap nhat va ve xe
        self._update_vehicles(light, n_vehicles)
        active_vehicles = self._vehicles[:min(n_vehicles, 6)]
        for v in active_vehicles:
            self._draw_vehicle(img, v, light)

        # Layer 4: ROI Stop Line (sau xe, de YOLO thay ro rang buoc)
        self._draw_stop_line(img, light)

        # Layer 5: Den giao thong
        self._draw_traffic_light(img, light, countdown)

        # Layer 6: Hieu ung thoi tiet
        self._draw_weather_fx(img, weather)

        # Layer 7: HUD overlay
        self._draw_hud(img, light, weather, len(active_vehicles), countdown)

        # Encode JPEG voi quality=8 (khop firmware ESP32-CAM, OCR-optimal)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, CAM_CFG["jpeg_quality"]]
        ok, buf = cv2.imencode(".jpg", img, encode_params)

        self.fidx += 1
        return buf.tobytes() if ok else np.zeros(512, dtype=np.uint8).tobytes()

    def render_violation(self, vehicle: dict, plate: str,
                         speed: float, conf: float) -> str:
        """
        Render anh chup vi pham cho payload["image_b64"].
        Khop voi _handle_violation() trong ai_engine.py:
        - Full frame + YOLO bounding box
        - Panel do vi pham top
        - Bien so ro rang de OCR
        Return: base64 string
        """
        light, countdown, _ = _traffic.get()
        img = np.zeros((CAM_H, CAM_W, 3), dtype=np.uint8)
        img[:] = (20, 25, 35)
        img[int(CAM_H * 0.44):] = (38, 44, 50)

        # Ve roi stop line noi bat
        roi_y1 = int(CAM_H * self.ROI_TOP)
        cv2.line(img, (0, roi_y1), (CAM_W, roi_y1), (50, 50, 230), 5)

        # Ve xe vi pham (DA QUA VACH)
        vx  = int(CAM_W * 0.35)
        vy  = roi_y1 + 22   # qua vach dung
        vw  = vehicle["w"]
        vc  = vehicle["color"]

        if vehicle["type"] == "CAR":
            cv2.rectangle(img, (vx, vy - 44), (vx + vw, vy + 12), vc, -1)
            cv2.rectangle(img, (vx + 7, vy - 38), (vx + vw - 7, vy - 21),
                          (160, 195, 215), -1)
            for wx in [vx + 14, vx + vw - 14]:
                cv2.circle(img, (wx, vy + 12), 9, (14, 14, 14), -1)
        else:
            hw = vw // 2
            cv2.ellipse(img, (vx + hw, vy - 5), (hw, 20), 0, 0, 360, vc, -1)
            for wx in [vx + 9, vx + vw - 9]:
                cv2.circle(img, (wx, vy + 7), 7, (14, 14, 14), -1)

        # Bien so ro rang (OCR target)
        cv2.rectangle(img, (vx + 3, vy + 1), (vx + 88, vy + 17), (240, 238, 25), -1)
        cv2.rectangle(img, (vx + 3, vy + 1), (vx + 88, vy + 17), (30, 30, 30), 1)
        cv2.putText(img, plate, (vx + 5, vy + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (12, 12, 12), 1, cv2.LINE_AA)

        # YOLO Bounding Box (khop voi cach ai_engine.py ve bbox)
        bx1 = vx - 20
        by1 = vy - 62
        bx2 = vx + vw + 20
        by2 = vy + 22
        box_color = (0, 0, 255)   # Mau do khi den do (khop ai_engine logic)
        cv2.rectangle(img, (bx1 - 3, by1 - 3), (bx2 + 3, by2 + 3), box_color, 3)

        # YOLO label (khop ai_engine format)
        yolo_label = "{} {:.0f}%".format(
            "motorcycle" if vehicle["type"] == "MOTORBIKE" else "car",
            conf * 100
        )
        lbl_bg_x2 = bx1 + len(yolo_label) * 9 + 10
        cv2.rectangle(img, (bx1, by1 - 22), (lbl_bg_x2, by1), box_color, -1)
        cv2.putText(img, yolo_label, (bx1 + 4, by1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)

        # Panel vi pham (top) — mau do dam
        cv2.rectangle(img, (0, 0), (CAM_W, 48), (0, 0, 155), -1)
        cv2.putText(img, "VI PHAM VUOT DEN DO  |  {}".format(self.cam_id.upper()),
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.64, (255, 255, 255), 2, cv2.LINE_AA)
        ts_str = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
        cv2.putText(img, ts_str,
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (210, 190, 190), 1, cv2.LINE_AA)

        # Thong tin vi pham ben phai panel
        cv2.putText(img, "BIEN SO: {}".format(plate),
                    (int(CAM_W * 0.42), 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.64, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(img,
            "{}  |  {:.1f} km/h  |  conf={:.2f}".format(vehicle["type"], speed, conf),
            (int(CAM_W * 0.42), 40),
            cv2.FONT_HERSHEY_SIMPLEX, 0.43, (215, 215, 215), 1, cv2.LINE_AA)

        # Watermark he thong
        cv2.putText(img, "AI TRAFFIC CONTROL SYSTEM v3.2  |  YOLOv8n + EasyOCR",
                    (10, CAM_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (65, 65, 100), 1, cv2.LINE_AA)

        # Encode JPEG quality 90 (anh vi pham luu o chat luong cao hon)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return base64.b64encode(buf.tobytes()).decode("utf-8") if ok else ""


# ════════════════════════════════════════════════════════════════════════════
# VIOLATION ENGINE — Mo phong YOLO detect + OCR tren ESP32
# ════════════════════════════════════════════════════════════════════════════
class ViolationEngine:
    """
    Mo phong pipeline AI chay tren ESP32-CAM:
    - YOLO detect xe trong ROI khi den do
    - OCR doc bien so (accuracy 90-95% khop thuc te)
    - Generate payload dung cho process_violation() cua app.py
    - Throttle 500ms (GH6), chi khi den do (GH5)
    - Chi detect MOTORBIKE + CAR (GH7)
    """

    # Regex bien so VN (khop _VN_PLATE_PATTERNS trong ai_engine.py)
    _VN_RE = re.compile(r"\d{2}[A-Z]{1,2}\d?-\d{4,5}", re.IGNORECASE)

    # Gioi han throttle (khop PLATE_THROTTLE_SEC trong ai_engine.py)
    PLATE_THROTTLE = 30   # giay

    def __init__(self, cam_id: str, renderer: SceneRenderer):
        self.cam_id      = cam_id
        self.renderer    = renderer
        self._last_ts    = 0.0         # timestamp violation cuoi (throttle 500ms)
        self._plate_seen: dict[str, float] = {}  # bien so da xu ly -> timestamp
        self._lock       = threading.Lock()

    def _simulate_ocr(self, plate_raw: str) -> str:
        """
        Mo phong EasyOCR voi accuracy 90-95%.
        Khop _run_ocr() trong ai_engine.py: replace O->0, I->1.
        """
        # Tinh toan accuracy: bien so ro (GH1 toc do thap) -> accuracy cao
        accuracy_roll = random.random()
        if accuracy_roll > 0.93:
            # OCR nham 1 ky tu (7% sai)
            chars = list(plate_raw)
            # Chi nham trong phan so, khong nham ma tinh/loai xe
            for i in range(len(chars) - 1, max(0, len(chars) - 5), -1):
                if chars[i].isdigit():
                    chars[i] = str(random.randint(0, 9))
                    break
            return "".join(chars)
        return plate_raw

    def try_detect(self, light: str, n_vehicles: int) -> dict | None:
        """
        Thu phat hien vi pham.
        Dieu kien: den DO + xe trong ROI + vuot vach + throttle 500ms.
        Khop logic _detection_loop + _handle_violation trong ai_engine.py.
        """
        if light != "RED":
            return None

        now = time.time()
        # GH6: 500ms capture interval
        with self._lock:
            if now - self._last_ts < CAPTURE_IV_S:
                return None

        # Xac suat vi pham: ~8%/chu ky de co du data nhung khong spam
        if random.random() > 0.08:
            return None

        # GH2: chi detect khi co xe trong ROI
        active = self.renderer._vehicles[:min(n_vehicles, 6)]
        if not active:
            return None

        # Chon xe vi pham ngau nhien (xe nao vuot den do)
        violator = random.choice(active)
        plate_raw = violator["plate"]

        # Throttle: khong phat hien bien so da xu ly trong 30s
        with self._lock:
            last_seen = self._plate_seen.get(plate_raw, 0)
            if now - last_seen < self.PLATE_THROTTLE:
                return None
            self._last_ts = now
            self._plate_seen[plate_raw] = now

        # OCR simulation
        plate_detected = self._simulate_ocr(plate_raw)

        # Speed: GH1 < 20 km/h (toc do thap giup OCR ro bien so)
        speed_kmh  = round(random.uniform(8.5, 18.5), 1)
        confidence = round(random.uniform(0.82, 0.97), 4)

        # Render anh vi pham (khop image_b64 field trong process_violation)
        image_b64 = self.renderer.render_violation(
            violator, plate_detected, speed_kmh, confidence
        )

        # Payload khop 100% process_violation() trong app.py
        return {
            "ts":             int(now),
            "plate":          plate_detected.strip().upper(),
            "type":           violator["type"],        # "MOTORBIKE" hoac "CAR" (GH7)
            "speed_kmh":      speed_kmh,               # GH1: < 20 km/h
            "confidence":     confidence,
            "image_b64":      image_b64,
            "cam_id":         self.cam_id,
            "roi":            "STOP_LINE",             # GH5
            "vehicles_frame": n_vehicles,              # GH2
            # Extra metadata (khop _handle_violation payload structure)
            "weather":        self.renderer._weather,  # GH3
            "distance":       5.0,                     # GH4 (5m)
            "capture_interval": CAPTURE_IV_S,          # GH6
        }


# ════════════════════════════════════════════════════════════════════════════
# CAMERA NODE — Mo phong day du 1 ESP32-CAM
# ════════════════════════════════════════════════════════════════════════════
class CameraNode:
    """
    Mo phong 1 ESP32-CAM vat ly:
    - Stream JPEG frames XGA lien tuc qua MQTT
    - Heartbeat status moi 4 giay (watchdog TTL 30s)
    - Context data GH1-GH7 moi 3 giay (chi cam_1 = primary)
    - Vi pham detection khi den do (cam_1 + cam_2)
    - ThingsBoard telemetry moi 10 giay
    - Nhiet do drift theo thoi gian (thuc te ESP32 nong dan)
    - WiFi RSSI drift ngau nhien (thuc te wifi fluctuate)
    """

    STATUS_IV    = 4.0    # s — heartbeat interval (app.py watchdog: 30s TTL)
    CONTEXT_IV   = 3.0    # s — context publish interval (cam_1 only)
    TB_IV        = 10.0   # s — ThingsBoard telemetry interval
    STATS_IV     = 60.0   # s — log stats interval

    def __init__(self, device_id: str, client: mqtt.Client):
        self.device_id  = device_id
        self.client     = client
        self.info       = DEVICES[device_id]
        self.is_camera  = (self.info["role"] == "camera")
        self.is_primary = self.info.get("primary", False)

        self.renderer   = SceneRenderer(device_id) if self.is_camera else None
        self.viol_eng   = (ViolationEngine(device_id, self.renderer)
                           if self.is_camera and not self.info.get("role") == "display"
                           else None)

        # Runtime counters
        self.start_ts     = time.time()
        self.frames_sent  = 0
        self.viols_sent   = 0
        self.status_sent  = 0

        # Sensor simulation (realistic drift)
        self._rssi_base   = random.uniform(76.0, 95.0)
        self._temp_base   = random.uniform(38.5, 43.5)
        self._rssi_phase  = random.uniform(0, 2 * math.pi)
        self._temp_phase  = random.uniform(0, 2 * math.pi)

        # Timers
        self._t_status   = 0.0
        self._t_context  = 0.0
        self._t_tb       = 0.0
        self._t_stats    = 0.0

        # Thoi tiet per-cam (moi camera co the o vi tri khac nhau)
        self._veh_count  = random.randint(2, 5)
        self._veh_ts     = time.time()

    # ── Sensor data simulation ────────────────────────────────────────────
    def _rssi(self) -> int:
        """RSSI WiFi drift theo hinh sin (thuc te WiFi fluctuate)."""
        t     = time.time() - self.start_ts
        drift = math.sin(t / 45 + self._rssi_phase) * 6.0
        noise = random.uniform(-2.0, 2.0)
        return int(max(40, min(100, self._rssi_base + drift + noise)))

    def _temp(self) -> float:
        """Nhiet do ESP32 tang dan theo thoi gian roi on dinh."""
        t     = time.time() - self.start_ts
        # Tan nhiet: +5°C trong 5 phut dau, roi dao dong nhe
        warmup = min(5.0, t / 60)
        drift  = math.sin(t / 90 + self._temp_phase) * 1.8
        noise  = random.uniform(-0.3, 0.3)
        return round(self._temp_base + warmup + drift + noise, 1)

    def _uptime(self) -> int:
        return int(time.time() - self.start_ts)

    # ── Payload builders ──────────────────────────────────────────────────
    def _status_payload(self) -> dict:
        """
        Khop 100% voi devices_state update trong app.py:
            devices_state[dev].update({
                "status": "ONLINE", "signal": d["rssi"], "temp": d["temp"],
                "uptime": d["uptime"], "last_seen": int(time.time()), "fw": d["fw"]
            })
        """
        return {
            "device_id": self.device_id,
            "rssi":      self._rssi(),
            "temp":      self._temp(),
            "uptime":    self._uptime(),
            "fw":        self.info["fw"],
        }

    def _context_payload(self) -> dict:
        """
        Khop 100% voi context_state update trong app.py _on_mqtt_message:
            context_state.update({
                "speed_kmh": ..., "vehicles_frame": ..., "weather": ...,
                "distance": ..., "capture_interval": ..., "roi": ...,
                "target_objects": ..., "fps": ...
            })
        7 Gioi han ngu canh toi uu:
        """
        light, _, _ = _traffic.get()
        # FIX v6.0: hasattr guard 3 lớp — tránh AttributeError khi SceneRenderer instance cũ
        if self.renderer and hasattr(self.renderer, "get_weather"):
            weather = self.renderer.get_weather()
        elif self.renderer and hasattr(self.renderer, "_get_weather"):
            weather = self.renderer._get_weather()
        elif self.renderer and hasattr(self.renderer, "_weather"):
            weather = self.renderer._weather
        else:
            weather = "SUN"

        # 3.5% anomaly de test frontend warning badges (khop thi truong thuc)
        anomaly = random.random() < 0.035
        if anomaly:
            log.warning("[%s] Context ANOMALY — test frontend validation", self.device_id)

        return {
            # GH1: Van toc < 20 km/h
            "speed_kmh":       round(random.uniform(21.5, 27.0) if anomaly
                                     else random.uniform(6.5, 19.0), 1),
            # GH2: So xe <= 6
            "vehicles_frame":  random.randint(7, 9) if anomaly
                               else random.randint(1, 5),
            # GH3: Thoi tiet
            "weather":         "HEAVY_RAIN" if anomaly else weather,
            # GH4: Khoang cach 5m
            "distance":        5.0,
            # GH5: ROI
            "roi":             "STOP_LINE",
            # GH6: 500ms
            "capture_interval": CAPTURE_IV_S,
            # GH7: Doi tuong
            "target_objects":  ["MOTORBIKE", "CAR"],
            # FPS thuc te
            "fps":             round(random.uniform(13.5, float(CAM_FPS)), 1),
        }

    def _thingsboard_telemetry(self) -> dict:
        """
        ThingsBoard telemetry (camera_AI device).
        Dap ung 8 cau hoi dashboard ThingsBoard.
        Khop cau truc _push_thingsboard trong app.py.
        """
        latency = random.randint(6, 42)
        total   = self.frames_sent + 1
        ok_rate = round((self.frames_sent - random.randint(0, max(1, self.frames_sent // 20))) / max(1, total), 3)
        return {
            # TELEMETRY cap nhat lien tuc
            "upload_ok":           1 if random.random() < 0.96 else 0,
            "last_http_code":      200 if random.random() < 0.96 else random.choice([408, 503, 429]),
            "latency_ms":          latency,
            "Wifi_Status":         self._rssi(),
            # Health metrics
            "uptime_s":            self._uptime(),
            "frames_sent":         self.frames_sent,
            "violations_detected": self.viols_sent,
            "upload_success_rate": ok_rate,
            # Camera config (khop server attributes ThingsBoard)
            "resolution":          "{}x{}".format(CAM_W, CAM_H),
            "jpeg_quality":        CAM_CFG["jpeg_quality"],
            "pixel_format":        CAM_CFG["pixel_format"],
            "fw_version":          self.info["fw"],
            "camera_id":           self.info.get("camera_id", self.device_id),
            "Model":               self.info.get("model", "ESP32"),
            "active":              True,
            "location":            json.dumps(self.info.get("location", {})),
        }

    # ── Vehicle count management ──────────────────────────────────────────
    def _get_vehicle_count(self, light: str) -> int:
        """So luong xe thuc te theo pha den (GH2: max 6)."""
        # Refresh so luong xe moi 8-15 giay (xe ra vao)
        now = time.time()
        if now - self._veh_ts > random.uniform(8.0, 15.0):
            if light == "RED":
                self._veh_count = random.randint(2, 5)
            elif light == "YELLOW":
                self._veh_count = random.randint(1, 4)
            else:
                self._veh_count = random.randint(0, 3)
            self._veh_ts = now
        return min(self._veh_count, 6)

    # ── Main loop ──────────────────────────────────────────────────────────
    def run(self):
        log.info("[%s] Node khoi dong | role=%s | FW=%s | IP=%s",
                 self.device_id, self.info["role"],
                 self.info["fw"], self.info["ip"])

        sleep_s = 1.0 / CAM_FPS  # ~66ms

        while _running.is_set():
            t0    = time.time()
            now   = t0
            light, countdown, mode = _traffic.get()

            # ═══ CAMERA NODES ═══════════════════════════════════════════
            if self.is_camera and self.renderer:
                n_veh = self._get_vehicle_count(light)

                # 1. STREAM FRAME — 15 FPS lien tuc
                #    app.py _on_mqtt_message: TOPIC_ESP32_FRAME -> latest_frame
                #    ai_engine: _get_frame() -> YOLO detect
                raw_bytes = self.renderer.render(n_veh)
                self.client.publish(TOPIC_ESP32_FRAME, raw_bytes, qos=0)
                self.frames_sent += 1

                # 2. DEVICE STATUS — moi 4s (watchdog TTL 30s)
                if now - self._t_status >= self.STATUS_IV:
                    status = self._status_payload()
                    self.client.publish(TOPIC_ESP32_STATUS, json.dumps(status), qos=1)
                    self.status_sent += 1
                    self._t_status = now

                # 3. CONTEXT DATA — chi cam_1 (primary), moi 3s
                #    app.py: context_state.update() + emit("context_update")
                if self.is_primary and now - self._t_context >= self.CONTEXT_IV:
                    ctx = self._context_payload()
                    self.client.publish(TOPIC_AI_CONTEXT, json.dumps(ctx), qos=1)
                    self._t_context = now

                # 4. VIOLATION DETECTION — cam_1 + cam_2, GH6: 500ms khi den do
                #    Neu den do + xe trong ROI + vuot vach -> publish violation
                #    app.py: process_violation() -> DB insert + emit("new_violation")
                if self.device_id in ("esp32_cam_1", "esp32_cam_2") and self.viol_eng:
                    viol = self.viol_eng.try_detect(light, n_veh)
                    if viol:
                        self.client.publish(TOPIC_AI_VIOLATION, json.dumps(viol), qos=1)
                        self.viols_sent += 1
                        log.warning(
                            "[%s] VI PHAM  plate=%-12s  type=%-10s  "
                            "%.1fkm/h  conf=%.2f  veh=%d",
                            self.device_id, viol["plate"], viol["type"],
                            viol["speed_kmh"], viol["confidence"], viol["vehicles_frame"]
                        )

                # 5. THINGSBOARD TELEMETRY — moi 10s
                if now - self._t_tb >= self.TB_IV:
                    # Khong publish len MQTT rieng (app.py tu push qua _push_thingsboard)
                    # Nhung log thong so de debug ThingsBoard dashboard
                    tb = self._thingsboard_telemetry()
                    log.debug("[%s] TB: upload_ok=%d latency=%dms wifi=%d fps=%.1f",
                              self.device_id, tb["upload_ok"], tb["latency_ms"],
                              tb["Wifi_Status"], tb.get("fps", 0))
                    self._t_tb = now

                # 6. STATS LOG — moi 60s
                if now - self._t_stats >= self.STATS_IV:
                    log.info("[%s] STATS: frames=%d viols=%d uptime=%ds rssi=%d temp=%.1fC",
                             self.device_id, self.frames_sent, self.viols_sent,
                             self._uptime(), self._rssi(), self._temp())
                    self._t_stats = now

            # ═══ CONTROLLER/DISPLAY NODES ═══════════════════════════════
            else:
                # esp32_main + esp32_led: chi gui status heartbeat
                if now - self._t_status >= self.STATUS_IV:
                    status = self._status_payload()
                    self.client.publish(TOPIC_ESP32_STATUS, json.dumps(status), qos=1)
                    self.status_sent += 1
                    self._t_status = now
                    # esp32_main: cung publish trang thai den hien tai
                    if self.device_id == "esp32_main":
                        pass  # Traffic state tu app.py quan ly, khong override

            # Giu dung FPS target
            elapsed = time.time() - t0
            time.sleep(max(0.0, sleep_s - elapsed))

        log.info("[%s] Node dung | frames=%d viols=%d uptime=%ds",
                 self.device_id, self.frames_sent, self.viols_sent, self._uptime())


# ════════════════════════════════════════════════════════════════════════════
# MQTT CLIENT FACTORY — Phong tranh DeprecationWarning cua paho v2
# ════════════════════════════════════════════════════════════════════════════
def _build_mqtt_client(client_id: str) -> mqtt.Client:
    # Direct mode (wired by app.py): no sockets/broker.
    if _DIRECT_ENABLED:
        c = _DirectMQTTClient(client_id)
        try:
            if callable(_DIRECT_SUBSCRIBE_LOCAL):
                _DIRECT_SUBSCRIBE_LOCAL(c.inject_message)
        except Exception:
            pass
        return c

    if _MQTT_API_V2:
        return mqtt.Client(
            client_id=client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        )
    return mqtt.Client(client_id=client_id)


# ════════════════════════════════════════════════════════════════════════════
# CLUSTER ORCHESTRATOR — Quan ly tat ca nodes + MQTT
# ════════════════════════════════════════════════════════════════════════════
class ClusterOrchestrator:
    """
    Quan ly toan bo cum thiet bi ao:
    - 1 MQTT connection dung chung cho tat ca nodes
    - Subscribe trang thai den tu server (TOPIC_TRAFFIC_STATE, TOPIC_CMD_*)
    - Khoi dong tat ca 5 nodes trong separate threads
    - Countdown local sync
    - Health monitoring
    """

    def __init__(self):
        self.client = _build_mqtt_client("VirtualCluster-{}".format(int(time.time()) % 999999))
        self.nodes: list[CameraNode] = []
        self._setup_callbacks()

    def _setup_callbacks(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                log.info("MQTT connected successfully -> %s:%d", MQTT_HOST, MQTT_PORT)
                # Subscribe trang thai den tu server — giong ESP32 thuc
                client.subscribe([
                    (TOPIC_TRAFFIC_STATE, 1),
                    (TOPIC_CMD_LIGHT,     1),
                    (TOPIC_CMD_EMERGENCY, 1),
                ])
                log.info("Subscribe: %s | %s | %s",
                         TOPIC_TRAFFIC_STATE, TOPIC_CMD_LIGHT, TOPIC_CMD_EMERGENCY)
            else:
                codes = {1:"Protocol", 2:"ClientID", 3:"ServerUnavail", 4:"BadAuth", 5:"NotAuthorized"}
                log.error("MQTT connect fail: rc=%d (%s)", rc, codes.get(rc, "Unknown"))

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                log.warning("MQTT disconnected rc=%d | auto-reconnect...", rc)

        def on_message(client, userdata, msg):
            """Xu ly lenh den tu server — giong esp32 thuc nhan command qua MQTT."""
            try:
                if msg.topic in (TOPIC_TRAFFIC_STATE, TOPIC_CMD_LIGHT):
                    d     = json.loads(msg.payload.decode())
                    light = d.get("light", "").upper()
                    if light in ("RED", "YELLOW", "GREEN"):
                        _traffic.server_update(
                            light,
                            int(d.get("countdown", 30)),
                            d.get("mode", "AUTO"),
                        )
                elif msg.topic == TOPIC_CMD_EMERGENCY:
                    d = json.loads(msg.payload.decode())
                    if d.get("active"):
                        l = d.get("light", "RED").upper()
                        _traffic.server_update(l, 60, "EMERGENCY")
                        log.warning("LENH KHAN CAP nhan duoc -> den: %s", l)
                    else:
                        l, cd, _ = _traffic.get()
                        _traffic.server_update(l, cd, "AUTO")
                        log.info("Emergency ended -> AUTO mode")
            except Exception as e:
                log.debug("on_message error: %s", e)

        self.client.on_connect    = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message    = on_message

    def _connect(self):
        """Ket noi MQTT voi retry logic."""
        if _DIRECT_ENABLED:
            # In-process bus: always "connected"
            try:
                self.client.connect(None, None, keepalive=MQTT_KEEPALIVE)
                self.client.loop_start()
            except Exception:
                pass
            log.info("DIRECT mode: connected (no broker).")
            return
        for attempt in range(1, 7):
            try:
                log.info("MQTT ket noi attempt %d/6 -> %s:%d...", attempt, MQTT_HOST, MQTT_PORT)
                self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
                self.client.loop_start()
                time.sleep(2.5)  # Doi on_connect callback
                return
            except Exception as e:
                log.error("MQTT attempt %d that bai: %s", attempt, e)
                if attempt < 6:
                    time.sleep(3 * attempt)
        log.critical("Khong the ket noi MQTT sau 6 lan. Kiem tra internet.")
        sys.exit(1)

    def _countdown_worker(self):
        """Dem nguoc local — fallback khi mat tin hieu server (giong ESP32 thuc)."""
        while _running.is_set():
            time.sleep(1.0)
            _traffic.local_tick()

    def start(self):
        broker_line = "DIRECT (in-process)" if _DIRECT_ENABLED else f"{MQTT_HOST}:{MQTT_PORT}"
        print(f"""
+=========================================================================+
|   VIRTUAL ESP32 CLUSTER v6.0  --  AI Traffic Control System             |
|   ASUS TUF GAMING A15  |  Replacing ESP32-CAM hardware                  |
+=========================================================================+
|   Broker   : {broker_line:<55}|
|   Dashboard: http://localhost:5050  (app.py must be running)            |
|   Devices  : 3x ESP32-CAM + ESP32 Main + LED 7-Segment                  |
|   Camera   : XGA 1024x768  |  JPEG Q=8  |  15 FPS                      |
|   7 Context Limits: GH1-speed GH2-veh GH3-wx GH4-dist GH5-roi          |
|                     GH6-interval GH7-target                             |
+=========================================================================+
""")

        # 1. Ket noi MQTT
        self._connect()

        # 2. Khoi dong countdown sync worker
        threading.Thread(target=self._countdown_worker,
                         name="CountdownSync", daemon=True).start()

        # 3. Khoi dong tat ca nodes
        for device_id, info in DEVICES.items():
            node = CameraNode(device_id, self.client)
            self.nodes.append(node)
            t = threading.Thread(
                target=node.run,
                name="Node-{}".format(device_id),
                daemon=True,
            )
            t.start()
            time.sleep(0.35)  # Stagger de tranh MQTT connection burst

        log.info("Cluster ready: %d nodes | %d FPS/cam | XGA %dx%d | JPEG Q=%d",
                 len(self.nodes), CAM_FPS, CAM_W, CAM_H, CAM_CFG["jpeg_quality"])
        log.info("Dashboard: http://localhost:5050")
        log.info("Logs vi pham xuat hien khi den DO, xem tai dashboard > Vi Pham")

        # 4. Main loop: health monitor + stats
        health_ts = time.time()
        try:
            while True:
                time.sleep(1)
                now = time.time()
                if now - health_ts >= 30:
                    health_ts = now
                    light, cd, mode = _traffic.get()
                    total_frames = sum(n.frames_sent for n in self.nodes)
                    total_viols  = sum(n.viols_sent  for n in self.nodes)
                    log.info(
                        "HEALTH | Den: %s(%ds) mode=%s | frames_total=%d "
                        "viols_total=%d | sync#%d tick#%d",
                        light, cd, mode, total_frames, total_viols,
                        _traffic.sync_count, _traffic.tick_count,
                    )
        except KeyboardInterrupt:
            print()
            log.info("Ctrl+C received — shutting down cluster...")
            _running.clear()
            time.sleep(1.5)
            try:
                self.client.disconnect()
                self.client.loop_stop()
            except Exception:
                pass
            log.info("Cluster stopped cleanly.")


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════
def main():
    orchestrator = ClusterOrchestrator()
    orchestrator.start()


if __name__ == "__main__":
    main()