# Edge YOLO worker for low-cost deployment on Raspberry Pi / Jetson
import os
import time
import requests
import cv2
from ultralytics import YOLO

BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:5050/api/ai-violation')
EDGE_TOKEN = os.getenv('EDGE_WEBHOOK_TOKEN', 'edge-webhook-token')
RTSP_URL = os.getenv('RTSP_URL', 'rtsp://user:pass@192.168.1.100:554/stream1')
MODEL_PATH = os.getenv('MODEL_PATH', 'yolov8n.pt')
CONF_THRESHOLD = float(os.getenv('CONF_THRESHOLD', '0.80'))

TARGET_CLASSES = {'no_helmet', 'triple', 'wrong_lane', 'red_light'}

model = YOLO(MODEL_PATH)


def post_violation(vtype, conf, lat=10.8231, lng=106.6297):
    payload = {
        'type': vtype,
        'conf': float(conf),
        'lat': lat,
        'lng': lng,
    }
    headers = {'x-edge-token': EDGE_TOKEN}
    try:
        requests.post(BACKEND_URL, json=payload, headers=headers, timeout=3)
    except Exception as exc:
        print(f'[edge] post failed: {exc}')


def main():
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open RTSP: {RTSP_URL}')

    print('[edge] started YOLO loop')
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.2)
            continue

        results = model(frame, verbose=False)
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                conf = float(box.conf.item())
                cls_idx = int(box.cls.item())
                label = result.names.get(cls_idx, str(cls_idx))
                if conf >= CONF_THRESHOLD and label in TARGET_CLASSES:
                    post_violation(label, conf)


if __name__ == '__main__':
    main()
