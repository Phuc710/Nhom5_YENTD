import requests
import time

# ====== CẤU HÌNH ======
TB_HOST = "https://tcm-iot.imespro.ai"
ACCESS_TOKEN = "MW4wkcsUVflWu9n1XWOP"

URL = f"{TB_HOST}/api/v1/{ACCESS_TOKEN}/telemetry"

phases = ["GREEN", "YELLOW", "RED"]
delay = 3  # giây

print("🚦 Bắt đầu test gửi đèn giao thông...")

while True:
    for phase in phases:
        payload = {
            "traffic_phase": phase
        }

        try:
            r = requests.post(URL, json=payload, timeout=5)
            print(f"Sent: {payload} | Status: {r.status_code}")
        except Exception as e:
            print("❌ Lỗi:", e)

        time.sleep(delay)
