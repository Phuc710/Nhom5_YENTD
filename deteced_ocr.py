import cv2
import torch
import numpy as np

# ========== PATHS ==========
DET_WEIGHTS = "LP_detector_nano_61.pt"   # model detect biển số (YOLOv5)
OCR_WEIGHTS = "LP_ocr_nano_62.pt"        # model OCR ký tự (YOLOv5)
IMAGE_PATH  = "2.jpg"
   
# ========== CONFIG ==========
DET_CONF = 0.25
OCR_CONF = 0.25
PLATE_PAD = 6      # padding crop biển số
SHOW_CROP = True   # show cửa sổ crop + text

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def decode_plate_text(det_chars, names, crop_h):
    """
    det_chars: numpy (N,6) [x1,y1,x2,y2,conf,cls]
    names: dict {cls_id: class_name} -> class_name là ký tự '0'..'9','A'..'Z'
    crop_h: chiều cao ảnh crop (để phân biệt 1 dòng/2 dòng)
    """
    if det_chars is None or len(det_chars) == 0:
        return ""

    # lấy center
    xs = (det_chars[:, 0] + det_chars[:, 2]) / 2.0
    ys = (det_chars[:, 1] + det_chars[:, 3]) / 2.0

    # Heuristic: nếu độ chênh y đủ lớn => 2 dòng
    y_range = ys.max() - ys.min()
    two_lines = y_range > 0.25 * crop_h  # bạn có thể chỉnh 0.20~0.35

    if not two_lines:
        # 1 dòng: sort theo x
        order = np.argsort(xs)
        chars = [str(names[int(det_chars[i, 5])]) for i in order]
        return "".join(chars)

    # 2 dòng: tách theo median y
    y_med = np.median(ys)
    top_idx = np.where(ys < y_med)[0]
    bot_idx = np.where(ys >= y_med)[0]

    # sort mỗi dòng theo x
    top_order = top_idx[np.argsort(xs[top_idx])] if len(top_idx) else []
    bot_order = bot_idx[np.argsort(xs[bot_idx])] if len(bot_idx) else []

    top = "".join([str(names[int(det_chars[i, 5])]) for i in top_order])
    bot = "".join([str(names[int(det_chars[i, 5])]) for i in bot_order])

    # format hiển thị
    if top and bot:
        return f"{top}-{bot}"   # bạn có thể đổi format theo ý
    return top + bot

# ===== Load models (YOLOv5 local repo) =====
det_model = torch.hub.load("yolov5", "custom", path=DET_WEIGHTS, source="local")
ocr_model = torch.hub.load("yolov5", "custom", path=OCR_WEIGHTS, source="local")

det_model.conf = DET_CONF
ocr_model.conf = OCR_CONF

# Read image
img0 = cv2.imread(IMAGE_PATH)
if img0 is None:
    raise FileNotFoundError(f"Không đọc được ảnh: {IMAGE_PATH}")
H, W = img0.shape[:2]

# Detect plates
det_res = det_model(img0)
plates = det_res.xyxy[0].cpu().numpy()  # [x1,y1,x2,y2,conf,cls]

if len(plates) == 0:
    print("❌ Không phát hiện biển số nào.")
    raise SystemExit

names_det = det_res.names
annotated = img0.copy()

# Loop all plates
for idx, p in enumerate(plates, start=1):
    x1, y1, x2, y2, conf, cls_id = p
    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

    # (tuỳ chọn) lọc đúng class license_plate
    # nếu model của bạn chỉ có 1 class thì khỏi cần
    if names_det.get(int(cls_id), "") not in ("license_plate", ""):
        continue

    # crop plate with padding
    xx1 = clamp(x1 - PLATE_PAD, 0, W - 1)
    yy1 = clamp(y1 - PLATE_PAD, 0, H - 1)
    xx2 = clamp(x2 + PLATE_PAD, 0, W - 1)
    yy2 = clamp(y2 + PLATE_PAD, 0, H - 1)

    plate_crop = img0[yy1:yy2, xx1:xx2].copy()
    if plate_crop.size == 0:
        continue

    # OCR on crop
    ocr_res = ocr_model(plate_crop)
    chars_det = ocr_res.xyxy[0].cpu().numpy()  # [x1,y1,x2,y2,conf,cls]
    names_ocr = ocr_res.names

    text = decode_plate_text(chars_det, names_ocr, crop_h=plate_crop.shape[0])

    # draw plate bbox
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)

    # draw text near bbox
    show_text = text if text else "N/A"
    cv2.putText(annotated, show_text, (x1, max(0, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)

    # show crop window (tuỳ chọn)
    if SHOW_CROP:
        crop_vis = plate_crop.copy()
        # vẽ bbox ký tự lên crop để debug (optional)
        for c in chars_det:
            cx1, cy1, cx2, cy2, cconf, ccls = c
            cx1, cy1, cx2, cy2 = map(int, [cx1, cy1, cx2, cy2])
            cv2.rectangle(crop_vis, (cx1, cy1), (cx2, cy2), (0, 255, 0), 2)
        cv2.putText(crop_vis, show_text, (5, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)

        cv2.imshow(f"Plate #{idx} Crop", crop_vis)

# Show final annotated image
cv2.namedWindow("Detected ALL + OCR", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Detected ALL + OCR", 1200, 700)
cv2.imshow("Detected ALL + OCR", annotated)

print("👉 Nhấn phím bất kỳ để đóng (ESC cũng được)")
cv2.waitKey(0)
cv2.destroyAllWindows()
