import time
import json
import uuid
import random
import paho.mqtt.client as mqtt
import requests

# ================= CONFIG =================
TB_PROVISION_URL = "https://tcm-iot.imespro.ai/api/v1/provision"
TB_MQTT_HOST = "103.249.117.212"
TB_MQTT_PORT = 1883

PROVISION_DEVICE_KEY = "3scp0hz740plm9k15vfj"
PROVISION_DEVICE_SECRET = "u7qws1jjqkecseragn3o"

DEVICE_PREFIX = "IMES_Cam_"
SEND_INTERVAL_SEC = 1

# ======= FIXED / FAKE ATTRS (client) =======
CAMERA_ID = random.randint(1, 50)
FW_VERSION = "1.0.0"
MODEL = "ESP32-CAM AI-THINKING"   # Model (tên device AI thinking)
LAT = 10.8231
LNG = 106.6297

# ================= GLOBAL =================
DEVICE_NAME = DEVICE_PREFIX + uuid.uuid4().hex[:8]
ACCESS_TOKEN = None
mqtt_client = None

# ---------------- Provision ----------------
def provision_device():
    global ACCESS_TOKEN

    payload = {
        "deviceName": DEVICE_NAME,
        "provisionDeviceKey": PROVISION_DEVICE_KEY,
        "provisionDeviceSecret": PROVISION_DEVICE_SECRET
    }

    r = requests.post(TB_PROVISION_URL, json=payload, timeout=10, verify=False)
    r.raise_for_status()
    data = r.json()

    ACCESS_TOKEN = (
        data.get("credentialsValue")
        or data.get("token")
        or data.get("ACCESS_TOKEN")
    )
    if not ACCESS_TOKEN:
        raise RuntimeError(f"Provision response missing token: {data}")

    print("[TB] Provision OK | Device:", DEVICE_NAME)
    print("[TB] Access token:", ACCESS_TOKEN)

# ---------------- Fake Upload Logic ----------------
def fake_upload_image():
    success = random.random() > 0.15
    latency = random.randint(80, 1200)
    http_code = 200 if success else random.choice([400, 401, 408, 500, 503])
    upload_ok = 1 if http_code == 200 else 0
    return upload_ok, http_code, latency

def fake_wifi_rssi():
    # RSSI dBm: -30 mạnh, -60 ổn, -80 yếu
    return random.randint(-85, -40)

# ---------------- Attributes (client) ----------------
def send_client_attributes():
    """
    CLIENT ATTRS bạn chốt:
    - Model
    - fw_version
    - camera_id
    - location (lat/lng)
    - Wifi_Status (dpm)  -> mình gửi thêm rssi và wifi_status
    """
    rssi = fake_wifi_rssi()
    payload = {
        "Model": MODEL,
        "fw_version": FW_VERSION,
        "camera_id": CAMERA_ID,
        "location": {"lat": LAT, "lng": LNG},
    }

    mqtt_client.publish("v1/devices/me/attributes", json.dumps(payload), qos=1)
    print("[ATTR client]", payload)

# ---------------- Telemetry ----------------
_fail_streak = 0

def send_telemetry():
    global _fail_streak

    upload_ok, http_code, latency = fake_upload_image()
    rssi = random.randint(-85, -40)

    if upload_ok == 0:
        _fail_streak += 1
        last_error = random.choice(["timeout", "dns_fail", "conn_refused", "server_error"])
    else:
        _fail_streak = 0
        last_error = ""

    payload = {
        "upload_ok": upload_ok,
        "last_http_code": http_code,
        "latency_ms": latency,

        "free_heap": random.randint(60000, 160000),
        "img_size_kb": random.randint(80, 300),

        "Wifi_Status": rssi,

        "upload_fail_count": _fail_streak,
        "last_seen": int(time.time() * 1000)
    }

    mqtt_client.publish(
        "v1/devices/me/telemetry",
        json.dumps(payload),
        qos=0
    )

    print("[TEL]", payload)


# ---------------- Optional: Read server attributes ----------------
def request_server_attributes():
    """
    Server attributes bạn chốt:
    fw_version, active, frames_per_upload, inactivityAlarmTime, jpeg_quality,
    lastActivityTime, lastConnectTime, lastDisconnectTime, pixel_format, reboot, resolution

    Device có thể "request" server attrs qua MQTT.
    Các key lastActivityTime/lastConnectTime/... thường do hệ thống tạo.
    """
    req_id = random.randint(1, 999999)
    payload = {
        "sharedKeys": "fw_version,active,frames_per_upload,inactivityAlarmTime,jpeg_quality,pixel_format,reboot,resolution"
    }
    mqtt_client.publish("v1/devices/me/attributes/request/" + str(req_id), json.dumps(payload), qos=1)
    print("[REQ server attrs] id=", req_id)

def on_message(client, userdata, msg):
    # Nhận response server attributes (nếu bạn request)
    topic = msg.topic
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return

    if topic.startswith("v1/devices/me/attributes/response/"):
        print("[RESP server attrs]", data)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Connected")
        client.subscribe("v1/devices/me/attributes/response/+")
        send_client_attributes()
        request_server_attributes()

def connect_mqtt():
    client = mqtt.Client(client_id=f"fake-{DEVICE_NAME}")
    client.username_pw_set(ACCESS_TOKEN)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(TB_MQTT_HOST, TB_MQTT_PORT, 60)
    client.loop_start()
    return client

# ================= MAIN =================
def main():
    global mqtt_client

    print("===== CAMERA AI FAKE DEVICE (IMES PRO) =====")
    print("Device:", DEVICE_NAME)

    provision_device()
    mqtt_client = connect_mqtt()

    time.sleep(2)

    while True:
        send_telemetry()
        time.sleep(SEND_INTERVAL_SEC)

if __name__ == "__main__":
    main()
