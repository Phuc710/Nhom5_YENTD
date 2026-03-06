"""
LICENSE PLATE - ULTRA LOW LATENCY MODE
- VGA 640x480, JPEG Q12, buffer=1
- Single OCR pass, fast preprocess only
- No bilateral filter (too slow)
- Frame skip: chỉ process mỗi 2 frame để không tắc queue
- Target: < 100ms end-to-end latency
"""

import sys
import cv2
import os
import torch
import numpy as np
import re
import time
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QMessageBox, QStatusBar, QCheckBox, QGroupBox, QTextEdit)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont
import function.helper as helper
from collections import Counter
import threading
from queue import Queue, Empty

# ============================================================
# CONFIG
# ============================================================
class Config:
    DETECTOR_MODEL  = "model/LP_detector_nano_61.pt"
    OCR_MODEL       = "model/LP_ocr_nano_62.pt"

    DETECTOR_CONF   = 0.45
    DETECTOR_IOU    = 0.35
    OCR_CONF        = 0.50

    ZONE_TOP        = 0.15
    ZONE_BOTTOM     = 0.85

    # OCR resize - nhỏ hơn = nhanh hơn, vẫn đủ cho YOLO OCR
    RESIZE_FACTOR   = 2.0          # Was 3.0 - cut 55% compute

    # Voting
    VOTE_WINDOW     = 20
    MIN_VOTES       = 3            # Lower = report faster

    # Latency control
    PROCESS_EVERY_N = 2            # Chỉ detect mỗi 2 frame - giảm tải
    OCR_QUEUE_SIZE  = 2            # Nhỏ = không backlog, drop stale frames
    DISPLAY_QUEUE   = 1            # Display chỉ giữ frame mới nhất

    SAVE_FOLDER     = "img"


# ============================================================
# FAST PREPROCESS - chỉ dùng operations nhanh
# ============================================================
def fast_preprocess(image):
    """Resize + CLAHE + sharpen - NO bilateral filter"""
    if image is None or image.size == 0:
        return image

    h, w = image.shape[:2]
    tw = int(w * Config.RESIZE_FACTOR)
    th = int(h * Config.RESIZE_FACTOR)

    # INTER_LINEAR nhanh hơn LANCZOS4 nhiều
    resized = cv2.resize(image, (tw, th), interpolation=cv2.INTER_LINEAR)

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)

    # Simple sharpen (3x3 - fastest)
    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]], dtype=np.float32)
    sharpened = cv2.filter2D(enhanced, -1, kernel)

    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def is_valid_plate(plate: str) -> bool:
    """Quick VN plate format check"""
    if not plate:
        return False
    p = plate.replace("-","").replace(".","").upper()
    if len(p) < 7 or len(p) > 10:
        return False
    if not p[:2].isdigit():
        return False
    return True


# ============================================================
# OCR WORKER - single thread, drop stale tasks
# ============================================================
class OCRWorker:
    def __init__(self, ocr_model):
        self.ocr_model   = ocr_model
        self.task_queue  = Queue(maxsize=Config.OCR_QUEUE_SIZE)
        self.result_queue= Queue()
        self.running     = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.3)
                if task is None:
                    break
                frame_id, crop, bbox = task
                processed = fast_preprocess(crop)
                lp = helper.read_plate(self.ocr_model, processed)
                if lp and lp != "unknown" and len(lp.replace("-","")) >= 7:
                    self.result_queue.put((frame_id, lp, bbox))
                self.task_queue.task_done()
            except Empty:
                continue
            except Exception:
                continue

    def submit(self, frame_id, crop, bbox):
        # Drop oldest if full (keep latest)
        if self.task_queue.full():
            try:
                self.task_queue.get_nowait()
            except Empty:
                pass
        try:
            self.task_queue.put_nowait((frame_id, crop, bbox))
        except Exception:
            pass

    def get_results(self):
        out = []
        while not self.result_queue.empty():
            try:
                out.append(self.result_queue.get_nowait())
            except Empty:
                break
        return out

    def stop(self):
        self.running = False
        try:
            self.task_queue.put_nowait(None)
        except Exception:
            pass


# ============================================================
# VOTING
# ============================================================
class PlateVoter:
    def __init__(self):
        self.history = []

    def add(self, plate):
        self.history.append(plate)
        if len(self.history) > Config.VOTE_WINDOW:
            self.history.pop(0)

    def consensus(self):
        if not self.history:
            return None, 0.0
        c = Counter(self.history)
        top, votes = c.most_common(1)[0]
        conf = votes / len(self.history) * 100
        if votes >= Config.MIN_VOTES:
            return top, conf
        return None, conf

    def best_guess(self):
        """Trả về kết quả tốt nhất kể cả chưa đủ votes"""
        if not self.history:
            return None, 0.0
        c = Counter(self.history)
        top, votes = c.most_common(1)[0]
        return top, votes / len(self.history) * 100

    def clear(self):
        self.history.clear()


# ============================================================
# DETECTION THREAD - low latency pipeline
# ============================================================
class DetectionThread(QThread):
    frame_signal  = pyqtSignal(object)
    plate_signal  = pyqtSignal(str, float)   # plate, confidence
    log_signal    = pyqtSignal(str)
    stats_signal  = pyqtSignal(dict)

    def __init__(self, detector, ocr_model):
        super().__init__()
        self.detector  = detector
        self.ocr       = OCRWorker(ocr_model)
        self.voter     = PlateVoter()

        self.frame_queue = Queue(maxsize=Config.DISPLAY_QUEUE)
        self.running     = False
        self._lock       = threading.Lock()
        self._latest     = None

        self.frame_count  = 0
        self.all_plates   = []
        self.enable_zone  = True
        self._last_emit   = 0.0   # throttle display emit

    def push_frame(self, frame):
        """Camera thread calls this. Always keep only the latest."""
        with self._lock:
            self._latest = frame

    def run(self):
        self.running = True
        process_ticker = 0

        while self.running:
            with self._lock:
                frame = self._latest
                self._latest = None

            if frame is None:
                self.msleep(5)
                continue

            self.frame_count += 1
            process_ticker += 1

            h, w = frame.shape[:2]
            zone_y1 = int(h * Config.ZONE_TOP)
            zone_y2 = int(h * Config.ZONE_BOTTOM)

            display = frame.copy()

            # Draw zone lines
            if self.enable_zone:
                cv2.line(display, (0, zone_y1), (w, zone_y1), (255, 120, 0), 1)
                cv2.line(display, (0, zone_y2), (w, zone_y2), (0, 220, 0), 1)

            # ---- DETECT every N frames ----
            if process_ticker >= Config.PROCESS_EVERY_N:
                process_ticker = 0

                with torch.no_grad():
                    results  = self.detector(frame, size=416)   # 416 faster than 640
                    det_list = results.pandas().xyxy[0].values.tolist()

                for d in det_list:
                    x1, y1, x2, y2 = int(d[0]), int(d[1]), int(d[2]), int(d[3])
                    conf = d[4]
                    bw, bh = x2 - x1, y2 - y1

                    if bw < 40 or bh < 12:
                        continue

                    cy = y1 + bh // 2
                    if self.enable_zone and not (zone_y1 <= cy <= zone_y2):
                        cv2.rectangle(display, (x1,y1),(x2,y2),(80,80,80),1)
                        continue

                    cv2.rectangle(display, (x1,y1),(x2,y2),(0,255,0),2)
                    cv2.putText(display, f"{conf:.2f}", (x1, y1-4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,0), 1)

                    # Crop + submit OCR
                    px = int(bw * 0.08)
                    py = int(bh * 0.10)
                    cx1 = max(0, x1-px); cy1 = max(0, y1-py)
                    cx2 = min(w, x2+px); cy2 = min(h, y2+py)
                    crop = frame[cy1:cy2, cx1:cx2].copy()

                    if crop.shape[0] >= 15 and crop.shape[1] >= 40:
                        self.ocr.submit(self.frame_count, crop, (x1,y1,bw,bh))

            # ---- Collect OCR results ----
            for fid, lp, bbox in self.ocr.get_results():
                self.all_plates.append(lp)
                self.voter.add(lp)
                plate_ok, conf_pct = self.voter.consensus()
                if plate_ok:
                    self.plate_signal.emit(plate_ok, conf_pct)
                self.log_signal.emit(f"[{datetime.now().strftime('%H:%M:%S')}] {lp}")

                # Draw label
                x, y, bw, bh = bbox
                cv2.rectangle(display, (x, y+bh+2),(x+100, y+bh+24),(0,200,0),-1)
                cv2.putText(display, lp, (x+3, y+bh+18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)

            # ---- Overlay consensus ----
            best, best_conf = self.voter.best_guess()
            if best:
                label = f"BSX: {best}  {best_conf:.0f}%"
                cv2.rectangle(display, (0, h-38),(260, h),(0,0,0),-1)
                color = (0,255,0) if best_conf >= 60 else (0,180,255)
                cv2.putText(display, label, (5, h-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            # ---- Emit display (throttle to ~30fps max) ----
            now = time.time()
            if now - self._last_emit >= 0.033:
                self._last_emit = now
                self.frame_signal.emit(display)

            self.stats_signal.emit({
                'frames': self.frame_count,
                'queue':  self.ocr.task_queue.qsize(),
                'total':  len(self.all_plates),
                'best':   best,
                'conf':   best_conf,
                'all':    Counter(self.all_plates)
            })

            self.msleep(1)

    def stop(self):
        self.running = False
        self.ocr.stop()
        self.wait()


# ============================================================
# CAMERA THREAD - minimal buffer, maximum freshness
# ============================================================
class CameraThread(QThread):
    status_signal = pyqtSignal(bool, str)

    def __init__(self, url, detection_thread):
        super().__init__()
        self.url = url
        self.det = detection_thread
        self.running = False

    def run(self):
        self.running = True
        cap = cv2.VideoCapture(self.url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # KEY: don't accumulate frames

        if not cap.isOpened():
            self.status_signal.emit(False, "Không kết nối được camera")
            return

        self.status_signal.emit(True, "Đã kết nối")
        fails = 0

        while self.running:
            ret, frame = cap.read()
            if not ret:
                fails += 1
                if fails > 15:
                    self.status_signal.emit(False, "Stream mất kết nối")
                    break
                time.sleep(0.03)
                continue
            fails = 0
            self.det.push_frame(frame)   # push vào detection, không block

        cap.release()

    def stop(self):
        self.running = False
        self.wait()


# ============================================================
# MAIN WINDOW
# ============================================================
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.esp_ip  = "192.168.1.148"
        self.cam     = None
        self.det     = None
        self.cur_frame = None
        self.recording = False
        self.vwriter   = None
        self.rx_count  = 0

        self.detector_model = None
        self.ocr_model      = None
        self._load_models()

        os.makedirs(Config.SAVE_FOLDER, exist_ok=True)
        os.makedirs(os.path.join(Config.SAVE_FOLDER, "best"), exist_ok=True)

        self._build_ui()

        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._tick_fps)

    def _load_models(self):
        try:
            dev = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.detector_model = torch.hub.load('ultralytics/yolov5','custom',
                                                  path=Config.DETECTOR_MODEL, force_reload=False)
            self.detector_model.conf = Config.DETECTOR_CONF
            self.detector_model.iou  = Config.DETECTOR_IOU
            self.detector_model.to(dev)

            self.ocr_model = torch.hub.load('ultralytics/yolov5','custom',
                                             path=Config.OCR_MODEL, force_reload=False)
            self.ocr_model.conf = Config.OCR_CONF
            self.ocr_model.to(dev)
            print(f"Models loaded on {dev}")
        except Exception as e:
            QMessageBox.critical(None,"Lỗi model", str(e))
            sys.exit(1)

    def _build_ui(self):
        self.setWindowTitle("🚗 Biển Số Xe - LOW LATENCY")
        self.setGeometry(100,100,1200,820)

        cw = QWidget(); self.setCentralWidget(cw)
        main = QHBoxLayout(); cw.setLayout(main)

        # --- LEFT ---
        left = QVBoxLayout()

        # Connection bar
        cg = QGroupBox("Camera")
        cl = QHBoxLayout()
        cl.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit(self.esp_ip); self.ip_edit.setMaximumWidth(150)
        cl.addWidget(self.ip_edit)
        self.btn_conn = QPushButton("Kết Nối")
        self.btn_conn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;padding:8px")
        self.btn_conn.clicked.connect(self.toggle_conn)
        cl.addWidget(self.btn_conn)
        cg.setLayout(cl); left.addWidget(cg)

        # Options
        og = QGroupBox("Tùy chọn")
        ol = QHBoxLayout()
        self.cb_zone = QCheckBox("Vùng nhận diện"); self.cb_zone.setChecked(True)
        self.cb_zone.stateChanged.connect(self._on_opt)
        ol.addWidget(self.cb_zone)
        og.setLayout(ol); left.addWidget(og)

        # Video
        self.vid = QLabel()
        self.vid.setAlignment(Qt.AlignCenter)
        self.vid.setStyleSheet("background:#111;color:#666;font-size:15px;border:2px solid #333")
        self.vid.setMinimumSize(800,600)
        self.vid.setText("Nhấn Kết Nối")
        left.addWidget(self.vid)

        # Buttons
        bl = QHBoxLayout()
        self.btn_cap = QPushButton("📸 Chụp"); self.btn_cap.setEnabled(False)
        self.btn_cap.setStyleSheet("background:#2196F3;color:white;font-weight:bold;padding:9px")
        self.btn_cap.clicked.connect(self._capture)
        bl.addWidget(self.btn_cap)
        self.btn_rec = QPushButton("🔴 Quay"); self.btn_rec.setEnabled(False)
        self.btn_rec.setStyleSheet("background:#f44336;color:white;font-weight:bold;padding:9px")
        self.btn_rec.clicked.connect(self._start_rec)
        bl.addWidget(self.btn_rec)
        self.btn_stop = QPushButton("⏹ Dừng"); self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background:#555;color:white;font-weight:bold;padding:9px")
        self.btn_stop.clicked.connect(self._stop_rec)
        bl.addWidget(self.btn_stop)
        left.addLayout(bl)

        # Stats row
        sl = QHBoxLayout()
        self.lbl_fps   = QLabel("FPS: --"); self.lbl_fps.setFont(QFont("Arial",10,QFont.Bold))
        self.lbl_frame = QLabel("F: 0")
        self.lbl_queue = QLabel("Q: 0")
        self.lbl_lat   = QLabel("Latency: --")
        for w in [self.lbl_fps, self.lbl_frame, self.lbl_queue, self.lbl_lat]:
            sl.addWidget(w)
        sl.addStretch()
        left.addLayout(sl)

        main.addLayout(left, 3)

        # --- RIGHT ---
        right = QVBoxLayout()
        rg = QGroupBox("Kết Quả")
        rl = QVBoxLayout()

        self.lbl_plate = QLabel("Biển số: ---")
        self.lbl_plate.setFont(QFont("Arial",20,QFont.Bold))
        self.lbl_plate.setStyleSheet("color:#4CAF50;padding:14px;background:#111;border-radius:6px;border:1px solid #4CAF50")
        self.lbl_plate.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.lbl_plate)

        self.lbl_conf = QLabel("Tin cậy: --")
        self.lbl_conf.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.lbl_conf)

        rl.addWidget(QLabel("Log:"))
        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(220)
        self.txt_log.setStyleSheet("background:#111;color:#bbb;font-family:Courier New;font-size:11px")
        rl.addWidget(self.txt_log)

        rl.addWidget(QLabel("Thống kê:"))
        self.txt_stats = QTextEdit(); self.txt_stats.setReadOnly(True)
        self.txt_stats.setStyleSheet("background:#111;color:#bbb;font-family:Courier New;font-size:11px")
        rl.addWidget(self.txt_stats)

        btn_reset = QPushButton("🔄 Reset")
        btn_reset.setStyleSheet("background:#FF9800;color:white;font-weight:bold;padding:8px")
        btn_reset.clicked.connect(self._reset)
        rl.addWidget(btn_reset)

        rg.setLayout(rl); right.addWidget(rg)
        main.addLayout(right, 1)

        self.statusBar().showMessage("Sẵn sàng")
        self._frame_ts = time.time()

    # ---- CONNECTION ----
    def toggle_conn(self):
        if self.cam and self.cam.isRunning():
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        self.esp_ip = self.ip_edit.text().strip()
        url = f"http://{self.esp_ip}/stream"
        self.btn_conn.setEnabled(False)
        self.statusBar().showMessage(f"Đang kết nối {url}...")

        self.det = DetectionThread(self.detector_model, self.ocr_model)
        self.det.frame_signal.connect(self._on_frame)
        self.det.plate_signal.connect(self._on_plate)
        self.det.log_signal.connect(self._on_log)
        self.det.stats_signal.connect(self._on_stats)
        self.det.start()

        self.cam = CameraThread(url, self.det)
        self.cam.status_signal.connect(self._on_status)
        self.cam.start()

        self.rx_count = 0
        self.fps_timer.start(1000)

    def _disconnect(self):
        if self.cam:  self.cam.stop();  self.cam = None
        if self.det:  self.det.stop();  self.det = None
        self.fps_timer.stop()
        if self.recording: self._stop_rec()

        self.btn_conn.setText("Kết Nối")
        self.btn_conn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;padding:8px")
        self.btn_conn.setEnabled(True)
        self.btn_cap.setEnabled(False)
        self.btn_rec.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.vid.setText("Đã ngắt kết nối")
        self.statusBar().showMessage("Ngắt kết nối")

    def _on_status(self, ok, msg):
        if ok:
            self.btn_conn.setText("Ngắt Kết Nối")
            self.btn_conn.setStyleSheet("background:#f44336;color:white;font-weight:bold;padding:8px")
            self.btn_conn.setEnabled(True)
            self.btn_cap.setEnabled(True)
            self.btn_rec.setEnabled(True)
            self.statusBar().showMessage(msg)
        else:
            QMessageBox.warning(self,"Lỗi",msg)
            self._disconnect()

    # ---- FRAME DISPLAY ----
    def _on_frame(self, frame):
        self.cur_frame = frame
        self.rx_count += 1

        # Latency indicator
        now = time.time()
        lat_ms = (now - self._frame_ts) * 1000
        self._frame_ts = now
        self.lbl_lat.setText(f"Lat: {lat_ms:.0f}ms")

        h, w, c = frame.shape
        qi = QImage(frame.data, w, h, c*w, QImage.Format_RGB888).rgbSwapped()
        px = QPixmap.fromImage(qi)
        self.vid.setPixmap(px.scaled(self.vid.size(), Qt.KeepAspectRatio, Qt.FastTransformation))

        if self.recording and self.vwriter:
            self.vwriter.write(frame)

    # ---- PLATE RESULT ----
    def _on_plate(self, plate, conf):
        color = "#4CAF50" if conf >= 65 else "#FF9800"
        self.lbl_plate.setText(f"Biển số: {plate}")
        self.lbl_plate.setStyleSheet(
            f"color:{color};padding:14px;background:#111;border-radius:6px;border:1px solid {color};font-size:20px;font-weight:bold")
        self.lbl_conf.setText(f"Tin cậy: {conf:.1f}%")

        # Auto-save
        if self.cur_frame is not None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = plate.replace("-","_")
            cv2.imwrite(os.path.join(Config.SAVE_FOLDER,"best",f"{safe}_{ts}.jpg"), self.cur_frame)

    def _on_log(self, msg):
        self.txt_log.append(msg)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_stats(self, stats):
        self.lbl_frame.setText(f"F:{stats['frames']}")
        self.lbl_queue.setText(f"Q:{stats['queue']}")

        c = stats['all']
        total = sum(c.values())
        if total == 0:
            return
        lines = [f"Tổng: {total}\n"]
        for i,(p,n) in enumerate(c.most_common(10),1):
            pct = n/total*100
            ok = "✓" if is_valid_plate(p) else " "
            lines.append(f"{i}. {ok} {p:14s} {n:3d}x {pct:5.1f}%")
        self.txt_stats.setText("\n".join(lines))

    def _on_opt(self):
        if self.det:
            self.det.enable_zone = self.cb_zone.isChecked()

    def _tick_fps(self):
        self.lbl_fps.setText(f"FPS:{self.rx_count}")
        self.rx_count = 0

    # ---- CAPTURE / RECORD ----
    def _capture(self):
        if self.cur_frame is None: return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p  = os.path.join(Config.SAVE_FOLDER, f"cap_{ts}.jpg")
        cv2.imwrite(p, self.cur_frame)
        self.statusBar().showMessage(f"Saved: {p}", 2000)

    def _start_rec(self):
        if self.cur_frame is None: return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p  = os.path.join(Config.SAVE_FOLDER, f"vid_{ts}.avi")
        h,w,_ = self.cur_frame.shape
        self.vwriter  = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*'XVID'), 15, (w,h))
        self.recording = True
        self.btn_rec.setEnabled(False); self.btn_stop.setEnabled(True)
        self.statusBar().showMessage(f"🔴 {p}")

    def _stop_rec(self):
        if self.vwriter: self.vwriter.release(); self.vwriter = None
        self.recording = False
        self.btn_rec.setEnabled(True); self.btn_stop.setEnabled(False)
        self.statusBar().showMessage("Đã dừng quay",3000)

    def _reset(self):
        if self.det:
            self.det.all_plates.clear()
            self.det.voter.clear()
        self.txt_log.clear(); self.txt_stats.clear()
        self.lbl_plate.setText("Biển số: ---")
        self.lbl_conf.setText("Tin cậy: --")

    def closeEvent(self, e):
        if self.recording: self._stop_rec()
        self._disconnect()
        e.accept()


# ============================================================
# ENTRY
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = App()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()