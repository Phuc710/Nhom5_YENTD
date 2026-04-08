import cv2
from ultralytics import YOLO

def main():
    # Sử dụng model YOLOv8 Medium (m)
    model_path = r"d:\ytd\backend\ml\yolov8m.pt"
    print(f"Loading model: {model_path}...")
    model = YOLO(model_path)

    # Mở webcam
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    print("YOLOv8m Vehicle Detection started. Press 'q' to quit.")

    # Class xe trong COCO: car(2), motorcycle(3), bus(5), truck(7)
    vehicle_ids = [2, 3, 5, 7]

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Chạy detect chỉ các loại phương tiện
        results = model(frame, classes=vehicle_ids, conf=0.2)[0]

        # Vẽ kết quả
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls  = int(box.cls[0])
            name = model.names[cls]

            # Vẽ bbox xanh lá cho xe
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{name} {conf:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Show frame
        cv2.imshow("YOLOv8m - Vehicle Detector", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()