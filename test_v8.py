import cv2
from ultralytics import YOLO

def main():
    # Load model YOLOv8
    model_path = r"d:\ytd\backend\ml\yolov8s.pt"
    print(f"Loading model: {model_path}...")
    model = YOLO(model_path)

    # Mở webcam (0 là camera mặc định)
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    print("Press 'q' to quit.")

    # Các class xe trong bộ COCO: 2(car), 3(motorcycle), 5(bus), 7(truck)
    vehicle_classes = [2, 3, 5, 7]

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Chạy detection (tạm thời bỏ filter class để xem model nhận diện cái gì)
        # Hạ confidence xuống 0.25 để dễ detect vật thể nhỏ/đồ chơi
        results = model(frame, conf=0.25)[0]

        # Vẽ bounding box thủ công cho từng vật thể detected
        for box in results.boxes:
            # Lấy tọa độ (x1, y1, x2, y2)
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls  = int(box.cls[0])
            name = model.names[cls]

            # Chọn màu xanh lá cho xe, các thứ khác màu xanh dương
            color = (0, 255, 0) if cls in [2, 3, 5, 7] else (255, 0, 0)

            # Vẽ hình chữ nhật (bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Vẽ label
            label = f"{name} {conf:.2f}"
            cv2.putText(frame, label, (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Hiển thị
        cv2.imshow("YOLOv8 Detection", frame)

        # Phím 'q' để thoát
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
