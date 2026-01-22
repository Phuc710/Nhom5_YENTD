import cv2
import torch
import numpy as np

WEIGHTS = "LP_detector_nano_61.pt"
IMAGE   = "2.jpg"

CONF_THRES = 0.25
PAD = 8

# Load YOLOv5 model
model = torch.hub.load("yolov5", "custom", path=WEIGHTS, source="local")
model.conf = CONF_THRES

img0 = cv2.imread(IMAGE)
if img0 is None:
    raise FileNotFoundError(f"Không đọc được ảnh: {IMAGE}")

H, W = img0.shape[:2]
results = model(img0)

det = results.xyxy[0].cpu().numpy()
if det.shape[0] == 0:
    print("❌ Không phát hiện biển số nào.")
    raise SystemExit

names = results.names
# lọc class license_plate nếu có
det_lp = []
for d in det:
    cls_id = int(d[5])
    if names.get(cls_id, "") == "license_plate":
        det_lp.append(d)
det_lp = np.array(det_lp) if len(det_lp) else det

# sort theo confidence
det_lp = det_lp[np.argsort(-det_lp[:, 4])]

annotated = img0.copy()
shown = 0

for i, d in enumerate(det_lp, start=1):
    x1, y1, x2, y2, conf, cls_id = d
    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

    # clamp + padding
    xx1 = max(0, x1 - PAD)
    yy1 = max(0, y1 - PAD)
    xx2 = min(W - 1, x2 + PAD)
    yy2 = min(H - 1, y2 + PAD)

    crop = img0[yy1:yy2, xx1:xx2].copy()
    if crop.size == 0:
        print(f"⚠️ Crop rỗng ở plate #{i}, bbox={(x1,y1,x2,y2)}")
        continue

    shown += 1

    # draw bbox on main image
    label = f"{names.get(int(cls_id), 'lp')} {conf:.2f}"
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(annotated, label, (x1, max(0, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # show each crop in its own window (KHÔNG bị đè)
    win = f"Plate Crop #{i}"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 520, 260)
    cv2.imshow(win, crop)

# show main window
cv2.namedWindow("Detected ALL", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Detected ALL", 1200, 700)
cv2.imshow("Detected ALL", annotated)

print(f"✅ Detected plates: {det_lp.shape[0]} | Crops shown: {shown}")
print("👉 Nhấn phím bất kỳ để đóng tất cả")
cv2.waitKey(0)
cv2.destroyAllWindows()
