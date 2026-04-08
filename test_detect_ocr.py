"""
test_detect_ocr.py — Detect + OCR biển số | Tracker ID + 1 xe 1 lần OCR.

Dùng:
    python test_detect_ocr.py                             # webcam
    python test_detect_ocr.py --source test1.mp4         # file video
    python test_detect_ocr.py --source http://IP/stream  # ESP32

Phím: Q/ESC=thoát  Z=zone  O=OCR  S=screenshot
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from backend.function.helper import read_plate as _ocr_fn
from backend.function.utils_rotate import changeContrast

# ── Config ────────────────────────────────────────────────────────────────────
DET_MODEL    = ROOT / "backend/ml/LP_detector.pt"
OCR_MODEL    = ROOT / "backend/ml/LP_ocr_nano_62.pt"
SMALL_W      = 80           # biển nhỏ → [S] tag
MIN_PLATE_W  = 60           # crop tối thiểu trước OCR (học từ OptimizedLPR)
MIN_AREA     = 800          # lọc bbox nhiễu (học từ OptimizedLPR)
PANEL_W      = 260
MAX_PLATES   = 12
AI_EVERY     = 3            # detect mỗi N frame
CROP_PAD     = 4            # padding khi crop biển (học từ OptimizedLPR)

DEFAULT_ZONE = np.array([
    [0.04, 0.22], [0.88, 0.15], [0.96, 0.68], [0.03, 0.64],
], dtype=np.float32)


# ── Simple IoU Tracker ─────────────────────────────────────────────────────────

def _iou(a, b):
    ix1, iy1 = max(a[0],b[0]), max(a[1],b[1])
    ix2, iy2 = min(a[2],b[2]), min(a[3],b[3])
    inter = max(0, ix2-ix1) * max(0, iy2-iy1)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0.0


class Tracker:
    """
    Gán tracking ID cho từng xe. OCR chỉ chạy 1 lần khi xe mới vào zone.
    Xe mất tích > MAX_LOST frame → xóa track.
    """
    MAX_LOST = 40   # ~4 giây tại 10fps
    IOU_THR  = 0.25

    def __init__(self):
        self.tracks = {}  # id -> {bbox, conf, text, ocr_done, lost}
        self._next  = 0

    def update(self, dets):
        """
        dets: list của [x1,y1,x2,y2,conf]
        Trả về dict {track_id: track_info}
        """
        matched_tids = set()
        result       = {}

        for det in dets:
            best_iou, best_tid = 0.0, None
            for tid, t in self.tracks.items():
                if tid in matched_tids: continue
                iou = _iou(det[:4], t["bbox"])
                if iou > best_iou:
                    best_iou, best_tid = iou, tid

            if best_iou >= self.IOU_THR and best_tid is not None:
                # Matched → cập nhật bbox
                self.tracks[best_tid].update({"bbox": det[:4], "conf": det[4], "lost": 0})
                matched_tids.add(best_tid)
                result[best_tid] = self.tracks[best_tid]
            else:
                # Xe mới
                tid = self._next; self._next += 1
                self.tracks[tid] = {
                    "bbox": det[:4], "conf": det[4],
                    "text": "", "zone_entered": False, "lost": 0,
                }
                matched_tids.add(tid)
                result[tid] = self.tracks[tid]

        # Tăng lost cho track không match
        for tid in list(self.tracks):
            if tid not in matched_tids:
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] >= self.MAX_LOST:
                    del self.tracks[tid]

        return result


# ── Load models ───────────────────────────────────────────────────────────────

def load_models(device="auto"):
    import torch
    dev = (device or "auto").strip().lower()
    if dev == "cuda": dev = "0"
    if dev in {"auto", ""}:
        if torch.cuda.is_available():
            try: torch.zeros(1).to("cuda"); dev = "0"
            except: dev = "cpu"
        else: dev = "cpu"
    print(f"\n🔧 Loading models on '{dev}'...")
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        det = torch.hub.load("ultralytics/yolov5", "custom",
                             path=str(DET_MODEL), force_reload=False,
                             device=dev, trust_repo=True)
        det.conf = 0.35
        ocr = torch.hub.load("ultralytics/yolov5", "custom",
                             path=str(OCR_MODEL), force_reload=False,
                             device=dev, trust_repo=True)
        ocr.conf = 0.45
        # Warmup: chạy dummy frame để GPU khởi động (học từ OptimizedLPR)
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        det(dummy, size=640)
    print(f"✅ Loaded {time.time()-t0:.1f}s | device={dev}\n")
    return det, ocr


# ── OCR ───────────────────────────────────────────────────────────────────────

def sr_upscale(img, scale):
    h, w = img.shape[:2]
    up   = cv2.resize(img, (w*scale, h*scale), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(up, (0,0), sigmaX=1.5)
    return cv2.addWeighted(up, 1.6, blur, -0.6, 0)


def read_plate(ocr, crop):
    h, w = crop.shape[:2]
    # Đảm bảo crop đủ rộng trước khi upscale (học từ OptimizedLPR)
    if w < MIN_PLATE_W:
        scale = MIN_PLATE_W / w
        crop  = cv2.resize(crop, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_LINEAR)
        w     = crop.shape[1]
    sc  = 6 if w < 40 else (4 if w < SMALL_W else (2 if w < 120 else 0))
    sr  = sr_upscale(crop, sc) if sc else crop
    enh = changeContrast(sr)
    t = _ocr_fn(ocr, enh)
    if t and t != "unknown" and len(t) >= 5: return t
    t = _ocr_fn(ocr, sr)
    if t and t != "unknown" and len(t) >= 5: return t
    return "unknown"


# ── Zone ──────────────────────────────────────────────────────────────────────

def in_zone(cx, cy, zone_px):
    return zone_px is None or \
           cv2.pointPolygonTest(zone_px, (float(cx), float(cy)), False) >= 0


def draw_zone(frame, zone_px):
    ov = frame.copy()
    cv2.fillPoly(ov, [zone_px], (72, 187, 120))
    cv2.addWeighted(ov, 0.15, frame, 0.85, 0, frame)
    cv2.polylines(frame, [zone_px], True, (72, 187, 120), 2)
    cx, cy = int(zone_px[:,0].mean()), int(zone_px[:,1].mean())
    cv2.rectangle(frame,(cx-55,cy-14),(cx+55,cy+8),(72,187,120),-1)
    cv2.putText(frame,"DETECT ZONE",(cx-50,cy+2),
                cv2.FONT_HERSHEY_SIMPLEX,0.48,(255,255,255),1)


# ── Panel ─────────────────────────────────────────────────────────────────────

def draw_panel(panel, detections):
    H = panel.shape[0]
    panel[:] = (25, 25, 35)
    cv2.rectangle(panel,(0,0),(PANEL_W,40),(45,45,60),-1)
    cv2.putText(panel,"DETECTED PLATES",(8,27),
                cv2.FONT_HERSHEY_SIMPLEX,0.5,(100,220,150),2)
    y = 50
    for d in detections[:MAX_PLATES]:
        if y + 76 > H: break
        cv2.rectangle(panel,(4,y),(PANEL_W-4,y+70),(40,40,55),-1)
        cv2.rectangle(panel,(4,y),(PANEL_W-4,y+70),(70,70,90),1)
        if d.get("thumb") is not None:
            try: panel[y+5:y+40, 8:68] = cv2.resize(d["thumb"],(60,35))
            except: pass
        color = (255,165,0) if d.get("tag")=="S" else (100,230,130)
        label = ("[S] " if d.get("tag")=="S" else "") + d["text"]
        cv2.putText(panel, label,              (72,y+22), cv2.FONT_HERSHEY_SIMPLEX,0.52,color,2)
        cv2.putText(panel, f"conf:{d['conf']:.2f}", (72,y+40), cv2.FONT_HERSHEY_SIMPLEX,0.37,(160,160,180),1)
        cv2.putText(panel, d["ts"],            (72,y+56), cv2.FONT_HERSHEY_SIMPLEX,0.34,(120,120,140),1)
        y += 76


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source",  default="0")
    ap.add_argument("--conf",    type=float, default=0.35)
    ap.add_argument("--device",  default="auto")
    ap.add_argument("--imgsz",   type=int,   default=640)
    ap.add_argument("--no-zone", action="store_true")
    ap.add_argument("--no-ocr",  action="store_true")
    ap.add_argument("--flip",    action="store_true")
    args = ap.parse_args()

    det, ocr = load_models(args.device)
    det.conf  = args.conf

    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print("❌ Không mở được source!"); sys.exit(1)
    print(f"🎥 Opened: {src!r}\n")

    cv2.namedWindow("Detect + OCR", cv2.WINDOW_NORMAL)

    zone_on    = not args.no_zone
    ocr_on     = not args.no_ocr
    flip_on    = args.flip
    fps_buf    = []
    detections = []       # panel
    seen_texts = set()    # dedup panel
    tracker    = Tracker()
    last_dets  = []
    frame_idx  = 0
    snap_n     = 0

    while True:
        t0 = time.monotonic()
        ok, frame = cap.read()
        if not ok or frame is None:
            print("⚠️  Hết video."); break

        if flip_on:
            frame = cv2.flip(frame, 1)

        H, W = frame.shape[:2]

        zone_px = (DEFAULT_ZONE * [[W,H]]).astype(np.int32) if zone_on else None

        # Detect mỗi AI_EVERY frame
        if frame_idx % AI_EVERY == 0:
            proc = changeContrast(frame)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = det(proc, size=args.imgsz).xyxy[0].cpu().numpy()
            # Lọc bbox quá nhỏ + sort lớn → nhỏ (học từ OptimizedLPR)
            filtered = [r.tolist() for r in raw
                        if (r[2]-r[0]) * (r[3]-r[1]) >= MIN_AREA]
            last_dets = sorted(filtered,
                               key=lambda r: (r[2]-r[0])*(r[3]-r[1]),
                               reverse=True)

        # Tracker update mỗi frame
        tracks = tracker.update(last_dets)

        for tid, t in tracks.items():
            x1,y1,x2,y2 = map(int, t["bbox"])
            conf     = t["conf"]
            plate_w  = x2 - x1
            is_small = plate_w < SMALL_W
            cx, cy   = (x1+x2)/2, (y1+y2)/2
            in_z     = in_zone(cx, cy, zone_px)

            # Clip to frame
            rx1,ry1 = max(0,x1), max(0,y1)
            rx2,ry2 = min(W,x2), min(H,y2)

            if not in_z:
                # Ngoài zone: vẽ bbox xám, vẫn tracking
                cv2.rectangle(frame,(x1,y1),(x2,y2),(90,90,90),1)
                cv2.putText(frame, f"#{tid}", (x1+2,y1+13),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150,150,150), 1)
                continue

            if rx2<=rx1 or ry2<=ry1: continue

            # ── Xe vừa VÀO zone lần đầu → OCR 1 lần ──────────────────────
            if ocr_on and not t["zone_entered"]:
                t["zone_entered"] = True          # đánh dấu đã vào zone
                # Padding khi crop (học từ OptimizedLPR)
                px1 = max(0, rx1 - CROP_PAD); py1 = max(0, ry1 - CROP_PAD)
                px2 = min(W, rx2 + CROP_PAD);  py2 = min(H, ry2 + CROP_PAD)
                crop = frame[py1:py2, px1:px2]
                if crop.size > 0:
                    text = read_plate(ocr, crop)
                    t["text"] = text
                    if text and text != "unknown" and text not in seen_texts:
                        seen_texts.add(text)
                        detections.insert(0, {
                            "text": text, "conf": conf,
                            "ts": time.strftime("%H:%M:%S"),
                            "thumb": crop.copy(),
                            "tag": "S" if is_small else "",
                        })
                        detections = detections[:30]
                        print(f"  [#{tid}] {'[S]' if is_small else ''} "
                              f"[{text}] conf={conf:.2f} w={plate_w}px")

            # ── Vẽ bbox trong zone ─────────────────────────────────────────
            color = (255,165,0) if is_small else (80,200,100)
            cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
            label = t["text"] if t["text"] and t["text"] != "unknown" else ""
            tag   = "[S] " if is_small else ""
            disp  = f"{tag}{label} {conf:.2f}" if label else f"{tag}{conf:.2f}"
            lw    = cv2.getTextSize(disp, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)[0][0]
            cv2.rectangle(frame,(x1,max(y1-24,0)),(x1+lw+8,y1),color,-1)
            cv2.putText(frame, disp, (x1+4,max(y1-6,12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0,0,0), 2, cv2.LINE_AA)
            cv2.putText(frame, f"#{tid} {plate_w}px", (x1,y2+13),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1)

        frame_idx += 1


        if zone_on and zone_px is not None:
            draw_zone(frame, zone_px)

        fps_buf.append(1.0 / max(time.monotonic()-t0, 1e-4))
        fps_buf = fps_buf[-30:]
        fps = sum(fps_buf) / len(fps_buf)
        for i, line in enumerate([
            f"FPS:{fps:.1f}  conf:{args.conf}",
            f"Zone:{'ON' if zone_on else 'OFF'}  OCR:{'ON' if ocr_on else 'OFF'}  Flip:{'ON' if flip_on else 'OFF'}",
            "Q=Quit Z=Zone O=OCR S=Snap M=Mirror",
        ]):
            y = 18 + i*18
            cv2.putText(frame, line, (6,y), cv2.FONT_HERSHEY_SIMPLEX,0.42,(0,0,0),3,cv2.LINE_AA)
            cv2.putText(frame, line, (6,y), cv2.FONT_HERSHEY_SIMPLEX,0.42,(255,255,100),1,cv2.LINE_AA)

        panel = np.zeros((H, PANEL_W, 3), dtype=np.uint8)
        draw_panel(panel, detections)
        cv2.imshow("Detect + OCR", np.hstack([frame, panel]))

        key = cv2.waitKey(1) & 0xFF
        if   key in (ord("q"), 27): break
        elif key == ord("z"):        zone_on = not zone_on
        elif key == ord("o"):        ocr_on  = not ocr_on
        elif key == ord("m"):        flip_on = not flip_on
        elif key == ord("s"):
            snap_n += 1; fname = f"snap_{snap_n:03d}.jpg"
            cv2.imwrite(fname, np.hstack([frame, panel]))
            print(f"  📸 {fname}")

    cap.release()
    cv2.destroyAllWindows()
    print("👋 Done.")


if __name__ == "__main__":
    main()
