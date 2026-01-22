import cv2
import torch

WEIGHTS = "LP_detector_nano_61.pt"
IMAGE   = "a_164337.jpg"

# Load YOLOv5 model (local repo)
model = torch.hub.load(
    "yolov5",
    "custom",
    path=WEIGHTS,
    source="local"
)

# Predict
results = model(IMAGE)

# Render bbox (zone) lên ảnh
img = results.render()[0]  # numpy BGR

# Hiển thị ảnh (KHÔNG tự đóng)
cv2.namedWindow("License Plate Zone", cv2.WINDOW_NORMAL)
cv2.resizeWindow("License Plate Zone", 1200, 700)
cv2.imshow("License Plate Zone", img)

print("👉 Nhấn phím bất kỳ để đóng cửa sổ")
cv2.waitKey(0)
cv2.destroyAllWindows()
