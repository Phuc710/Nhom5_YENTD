import cv2
import torch
import numpy as np

WEIGHTS = "LP_detector_nano_61.pt"
IMAGE   = "3.jpg"

# Load YOLOv5 model (local repo)
model = torch.hub.load("yolov5", "custom", path=WEIGHTS, source="local")

# Read image (BGR)
img0 = cv2.imread(IMAGE)
if img0 is None:
    raise FileNotFoundError(f"Không đọc được ảnh: {IMAGE}")

# Predict
results = model(img0)

# Lấy tất cả detection: [x1, y1, x2, y2, conf, cls]
det = results.xyxy[0].cpu().numpy()

if det.shape[0] == 0:
    print("❌ Không phát hiện biển số nào.")
    raise SystemExit

# Nếu muốn chỉ lấy đúng class 'license_plate' (nếu model có nhiều class)
# class_name_to_keep = "license_plate"
# names = results.names  # dict {id: name}
# det = np.array([d for d in det if names[int(d[5])] == class_name_to_keep])
# if det.shape[0] == 0:
#     print("❌ Không có detection đúng class license_plate.")
#     raise SystemExit

# Chọn bbox có confidence cao nhất
best = det[np.argmax(det[:, 4])]
x1, y1, x2, y2, conf, cls_id = best
x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

# Padding để crop rộng hơn chút (tuỳ chỉnh)
pad = 8
h, w = img0.shape[:2]
x1 = max(0, x1 - pad)
y1 = max(0, y1 - pad)
x2 = min(w - 1, x2 + pad)
y2 = min(h - 1, y2 + pad)

# Crop biển số
plate_crop = img0[y1:y2, x1:x2].copy()

# Hiển thị ảnh gốc có bbox (tuỳ chọn)
img_draw = img0.copy()
cv2.rectangle(img_draw, (x1, y1), (x2, y2), (0, 0, 255), 2)
label = f"{results.names[int(cls_id)]} {conf:.2f}"
cv2.putText(img_draw, label, (x1, max(0, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)

# Show (không tự đóng)
cv2.namedWindow("Detected", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Detected", 1200, 700)
cv2.imshow("Detected", img_draw)

cv2.namedWindow("Plate Crop", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Plate Crop", 500, 250)
cv2.imshow("Plate Crop", plate_crop)

# Save crop
cv2.imwrite("plate_crop.jpg", plate_crop)
print("✅ Saved crop: plate_crop.jpg")
print("👉 Nhấn phím bất kỳ để đóng")
cv2.waitKey(0)
cv2.destroyAllWindows()
