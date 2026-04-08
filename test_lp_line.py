"""
test_lp_line.py  —  LP Detect + OCR + Tracking  (PyQt5 UI)
────────────────────────────────────────────────────────────
Cách chạy:
    python test_lp_line.py                          # webcam
    python test_lp_line.py test2.mp4                # video file
    python test_lp_line.py "C:/path/video.mp4"
"""
import sys, os, math, warnings, time
from pathlib import Path

import cv2
import numpy as np
import torch

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QSizePolicy, QScrollArea,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QImage, QPixmap, QColor, QFont, QIcon

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE  = Path(__file__).parent
DET_W = BASE / "backend/ml/LP_detector.pt"
OCR_W = BASE / "backend/ml/LP_ocr.pt"

# ─── Config ──────────────────────────────────────────────────────────────────
CONF_DET  = 0.35
CONF_OCR  = 0.45
IMGSZ     = 640
TRACK_IOU = 0.35
MAX_MISS  = 8     # frames tối đa mất track trước khi xóa

# ─── Helpers (inline, không import backend) ───────────────────────────────────
def _iou(a, b):
    ix1=max(a[0],b[0]); iy1=max(a[1],b[1])
    ix2=min(a[2],b[2]); iy2=min(a[3],b[3])
    inter=max(0,ix2-ix1)*max(0,iy2-iy1)
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
    return inter/union if union>0 else 0.0

def _clahe(img):
    lab=cv2.cvtColor(img,cv2.COLOR_BGR2LAB)
    l,a,b=cv2.split(lab)
    l=cv2.createCLAHE(2.0,(8,8)).apply(l)
    return cv2.cvtColor(cv2.merge([l,a,b]),cv2.COLOR_LAB2BGR)

def _sr(crop, scale=4):
    h,w=crop.shape[:2]
    up=cv2.resize(crop,(w*scale,h*scale),interpolation=cv2.INTER_LANCZOS4)
    blur=cv2.GaussianBlur(up,(0,0),1.5)
    return cv2.addWeighted(up,1.6,blur,-0.6,0)

def _on_line(x,y,x1,y1,x2,y2):
    if x2==x1: return True
    a=(y2-y1)/(x2-x1); b=y1-a*x1
    return math.isclose(a*x+b, y, abs_tol=3)

def read_plate(ocr_model, im):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res=ocr_model(im)
    bbs=res.pandas().xyxy[0].values.tolist()
    if len(bbs)<5 or len(bbs)>12: return "unknown"
    centers=[]; y_sum=0
    for bb in bbs:
        xc=(bb[0]+bb[2])/2; yc=(bb[1]+bb[3])/2
        y_sum+=yc; centers.append([xc,yc,bb[-1]])
    l_pt=min(centers,key=lambda c:c[0]); r_pt=max(centers,key=lambda c:c[0])
    lp_type="1"
    for c in centers:
        if l_pt[0]!=r_pt[0] and not _on_line(c[0],c[1],l_pt[0],l_pt[1],r_pt[0],r_pt[1]):
            lp_type="2"; break
    y_mean=int(y_sum/len(centers)); plate=""
    if lp_type=="2":
        r1=sorted([c for c in centers if c[1]<=y_mean],key=lambda c:c[0])
        r2=sorted([c for c in centers if c[1]> y_mean],key=lambda c:c[0])
        plate="".join(str(c[2]) for c in r1)+"-"+"".join(str(c[2]) for c in r2)
    else:
        plate="".join(str(c[2]) for c in sorted(centers,key=lambda c:c[0]))
    return plate if len(plate)>=5 else "unknown"

def load_model(path, conf):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m=torch.hub.load("ultralytics/yolov5","custom",
                         path=str(path),force_reload=False,trust_repo=True)
    m.conf=conf; m.eval(); return m

# ─── Tracker ─────────────────────────────────────────────────────────────────
class Track:
    _cnt=0
    def __init__(self,bbox):
        Track._cnt+=1
        self.tid=Track._cnt; self.bbox=bbox
        self.missed=0; self.crossed=False; self.ocr_done=False

class SimpleTracker:
    def __init__(self,iou_thr=0.35,max_miss=8):
        self.tracks=[]; self.iou_thr=iou_thr; self.max_miss=max_miss

    def update(self,dets):
        matched_t=set(); matched_d=set(); pairs=[]
        for di,det in enumerate(dets):
            for ti,tr in enumerate(self.tracks):
                v=_iou(det[:4],tr.bbox)
                if v>=self.iou_thr: pairs.append((v,di,ti))
        pairs.sort(reverse=True,key=lambda x:x[0])
        for _,di,ti in pairs:
            if di in matched_d or ti in matched_t: continue
            self.tracks[ti].bbox=dets[di][:4]
            self.tracks[ti].missed=0
            matched_d.add(di); matched_t.add(ti)
        for di,det in enumerate(dets):
            if di not in matched_d: self.tracks.append(Track(det[:4]))
        active_ids={self.tracks[ti].tid for ti in matched_t}
        for tr in self.tracks:
            if tr.tid not in active_ids: tr.missed+=1
        self.tracks=[t for t in self.tracks if t.missed<=self.max_miss]
        return self.tracks

# ─── Worker thread ───────────────────────────────────────────────────────────
class DetectWorker(QThread):
    # (frame_rgb, tracks_snapshot, y_line)
    frame_ready  = pyqtSignal(object, list, int)
    plate_found  = pyqtSignal(str, object)   # (plate_text, crop_bgr)
    status_msg   = pyqtSignal(str)

    def __init__(self, src, det_model, ocr_model):
        super().__init__()
        self.src=src; self.det=det_model; self.ocr=ocr_model
        self._running=True

    def stop(self): self._running=False

    def run(self):
        cap=cv2.VideoCapture(self.src)
        if not cap.isOpened():
            self.status_msg.emit(f"❌ Không mở được: {self.src}"); return

        # Đọc frame đầu để lấy kích thước gốc
        ret, f0=cap.read()
        if not ret: self.status_msg.emit("❌ Không đọc được frame"); cap.release(); return
        H,W=f0.shape[:2]
        Y_LINE=H//2
        cap.set(cv2.CAP_PROP_POS_FRAMES,0)  # rewind

        tracker=SimpleTracker(iou_thr=TRACK_IOU,max_miss=MAX_MISS)
        plate_set=set()

        while self._running:
            ret,raw=cap.read()
            if not ret: break

            frame=_clahe(raw)  # giữ nguyên size gốc

            # Detect
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dets_np=self.det(frame,size=IMGSZ).xyxy[0].cpu().numpy()
            dets=[(d[0],d[1],d[2],d[3],d[4]) for d in dets_np
                  if (d[2]-d[0])*(d[3]-d[1])>400]

            tracks=tracker.update(dets)
            snap=[]

            for tr in tracks:
                x1,y1,x2,y2=[int(v) for v in tr.bbox]
                cy=(y1+y2)//2
                just_crossed=False
                if not tr.crossed and cy>=Y_LINE:
                    tr.crossed=True; just_crossed=True

                snap.append({
                    "tid":tr.tid,"bbox":(x1,y1,x2,y2),
                    "crossed":tr.crossed
                })

                if just_crossed and not tr.ocr_done and self.ocr:
                    tr.ocr_done=True
                    pad=10
                    crop=frame[max(0,y1-pad):min(H,y2+pad),
                               max(0,x1-pad):min(W,x2+pad)].copy()
                    if crop.size>0:
                        crop_enh=_clahe(crop)
                        crop_sr =_sr(crop_enh,scale=4)
                        plate=read_plate(self.ocr,crop_sr)
                        if plate=="unknown":
                            plate=read_plate(self.ocr,crop_enh)
                        label=plate if plate!="unknown" else f"ID{tr.tid}(?)"
                        if label not in plate_set:
                            plate_set.add(label)
                            self.plate_found.emit(label, crop)
                            print(f"[OCR] ID{tr.tid} → {label}")

            # Vẽ HUD lên frame gốc (BGR), rồi chuyển RGB gửi lên UI
            vis=raw.copy()
            # Detection line
            cv2.line(vis,(0,Y_LINE),(W,Y_LINE),(0,200,255),2)
            cv2.putText(vis,"DETECTION LINE",(10,Y_LINE-8),
                        cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,200,255),1,cv2.LINE_AA)
            # Bounding boxes
            for tr_info in snap:
                x1,y1,x2,y2=tr_info["bbox"]
                color=(0,255,100) if tr_info["crossed"] else (160,160,160)
                cv2.rectangle(vis,(x1,y1),(x2,y2),color,2)
                cv2.putText(vis,f"ID{tr_info['tid']}",(x1,y1-4),
                            cv2.FONT_HERSHEY_SIMPLEX,0.45,color,1,cv2.LINE_AA)

            rgb=cv2.cvtColor(vis,cv2.COLOR_BGR2RGB)
            self.frame_ready.emit(rgb, snap, Y_LINE)

        cap.release()
        self.status_msg.emit("✅ Xong")

# ─── UI ──────────────────────────────────────────────────────────────────────
THUMB_W, THUMB_H = 140, 45

def bgr_to_pixmap(bgr):
    h,w=bgr.shape[:2]
    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
    qi=QImage(rgb.data,w,h,w*3,QImage.Format_RGB888)
    return QPixmap.fromImage(qi)

class PlateItem(QWidget):
    def __init__(self, text, crop_bgr):
        super().__init__()
        self.setFixedHeight(THUMB_H+12)
        lay=QHBoxLayout(self); lay.setContentsMargins(4,4,4,4); lay.setSpacing(8)

        # Thumbnail
        thumb_lbl=QLabel()
        if crop_bgr is not None:
            px=bgr_to_pixmap(crop_bgr).scaled(THUMB_W,THUMB_H,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        else:
            px=QPixmap(THUMB_W,THUMB_H); px.fill(QColor(30,30,30))
        thumb_lbl.setPixmap(px)
        thumb_lbl.setFixedSize(THUMB_W,THUMB_H)
        lay.addWidget(thumb_lbl)

        # Text
        txt_lbl=QLabel(text)
        txt_lbl.setStyleSheet("color:#32FF8C;font-size:14px;font-weight:bold;")
        txt_lbl.setWordWrap(True)
        lay.addWidget(txt_lbl, 1)
        self.setStyleSheet("background:#1a1a2e;border-bottom:1px solid #2a2a4a;")

class MainWindow(QMainWindow):
    def __init__(self, src, det_model, ocr_model):
        super().__init__()
        self.setWindowTitle("LP Detection — Line Crossing")
        self.setStyleSheet("background:#0d0d1a;color:white;")

        # ── Central widget ──────────────────────────────────────────────────
        central=QWidget(); self.setCentralWidget(central)
        root_lay=QHBoxLayout(central); root_lay.setContentsMargins(0,0,0,0); root_lay.setSpacing(0)

        # Video label
        self.video_lbl=QLabel()
        self.video_lbl.setAlignment(Qt.AlignCenter)
        self.video_lbl.setStyleSheet("background:#000;")
        self.video_lbl.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        root_lay.addWidget(self.video_lbl, 1)

        # Right panel
        panel=QWidget(); panel.setFixedWidth(240)
        panel.setStyleSheet("background:#10102a;")
        p_lay=QVBoxLayout(panel); p_lay.setContentsMargins(0,0,0,0); p_lay.setSpacing(0)

        hdr=QLabel("  🚗 BIỂN SỐ")
        hdr.setFixedHeight(36)
        hdr.setStyleSheet("background:#1e1e4a;color:#FFD700;font-size:14px;font-weight:bold;")
        p_lay.addWidget(hdr)

        self.plate_list=QListWidget()
        self.plate_list.setStyleSheet("""
            QListWidget { background:#10102a; border:none; }
            QListWidget::item { border:none; padding:0; }
            QScrollBar:vertical { width:6px; background:#1a1a3a; }
            QScrollBar::handle:vertical { background:#3a3a6a; border-radius:3px; }
        """)
        p_lay.addWidget(self.plate_list, 1)

        self.count_lbl=QLabel("  0 biển")
        self.count_lbl.setFixedHeight(28)
        self.count_lbl.setStyleSheet("background:#1a1a3a;color:#888;font-size:12px;")
        p_lay.addWidget(self.count_lbl)

        root_lay.addWidget(panel)

        # ── Status bar ──────────────────────────────────────────────────────
        self.statusBar().setStyleSheet("background:#0a0a1a;color:#666;")
        self.statusBar().showMessage("Loading models …")

        # ── Worker ──────────────────────────────────────────────────────────
        self.worker=DetectWorker(src, det_model, ocr_model)
        self.worker.frame_ready.connect(self.on_frame)
        self.worker.plate_found.connect(self.on_plate)
        self.worker.status_msg.connect(self.statusBar().showMessage)
        self.worker.start()

        self._plate_count=0

    def on_frame(self, rgb, snap, y_line):
        h,w=rgb.shape[:2]
        qi=QImage(rgb.data,w,h,w*3,QImage.Format_RGB888)
        px=QPixmap.fromImage(qi)
        # Scale giữ tỷ lệ vừa với label
        lbl_sz=self.video_lbl.size()
        px_scaled=px.scaled(lbl_sz,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        self.video_lbl.setPixmap(px_scaled)

    def on_plate(self, text, crop_bgr):
        self._plate_count+=1
        item=QListWidgetItem()
        w=PlateItem(text, crop_bgr)
        item.setSizeHint(w.sizeHint())
        self.plate_list.insertItem(0, item)          # thêm lên đầu (mới nhất trên cùng)
        self.plate_list.setItemWidget(item, w)
        self.count_lbl.setText(f"  {self._plate_count} biển")

    def closeEvent(self, e):
        self.worker.stop()
        self.worker.wait(3000)
        super().closeEvent(e)

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    app=QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    src = sys.argv[1] if len(sys.argv)>1 else 0
    try: src=int(src)
    except (ValueError, TypeError): pass

    print("[INFO] Loading models …")
    det_model=load_model(DET_W, CONF_DET)
    ocr_model=load_model(OCR_W, CONF_OCR) if OCR_W.exists() else None
    print("[INFO] Models OK")

    # Lấy size video để đặt cửa sổ
    cap=cv2.VideoCapture(src)
    vid_w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    win=MainWindow(src, det_model, ocr_model)
    win.resize(vid_w+240, vid_h)   # video size + panel 240px
    win.show()

    sys.exit(app.exec_())

if __name__=="__main__":
    main()
