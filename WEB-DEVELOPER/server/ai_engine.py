import cv2
import time
import json
import threading
import paho.mqtt.client as mqtt
from ultralytics import YOLO
import easyocr

MQTT_HOST = "broker.hivemq.com"
MQTT_PORT = 1883

TOPIC_CONTEXT = "traffic/ai/context"

CAMERA_SOURCE = 0

mqtt_client = mqtt.Client()
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()

print("Loading YOLO...")
vehicle_model = YOLO("yolov8n.pt")

print("Loading OCR...")
ocr_reader = easyocr.Reader(['en'])

print("AI Engine Ready")

def is_vehicle(cls_name):
    return cls_name in ["car", "motorcycle", "bus", "truck"]

def ai_loop(app):

    global_frame = None

    cap = cv2.VideoCapture(CAMERA_SOURCE)

    if not cap.isOpened():
        print("❌ Cannot open laptop camera")
        return

    print("🎥 Laptop camera started")

    while True:

        ret, frame = cap.read()
        if not ret:
            continue

        results = vehicle_model(frame, verbose=False)[0]

        vehicles_in_frame = 0

        for box in results.boxes:
            cls_id = int(box.cls[0])
            cls_name = vehicle_model.names[cls_id]

            if not is_vehicle(cls_name):
                continue

            vehicles_in_frame += 1

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)
            cv2.putText(frame,
                        f"{cls_name} {round(conf*100,1)}%",
                        (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0,255,0),
                        2)

        # 🔥 UPDATE GLOBAL FRAME IN APP
        app.latest_frame = frame.copy()

        context_payload = {
            "vehicles": vehicles_in_frame,
            "ts": int(time.time())
        }

        mqtt_client.publish(TOPIC_CONTEXT, json.dumps(context_payload))

        time.sleep(0.03)

def start_ai(app):
    app.latest_frame = None
    thread = threading.Thread(target=ai_loop, args=(app,), daemon=True)
    thread.start()
    print("AI Engine Thread Started")
