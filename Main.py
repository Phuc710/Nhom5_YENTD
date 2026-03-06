"""
HỆ THỐNG NHẬN DIỆN BIỂN SỐ XE - LICENSE PLATE RECOGNITION SYSTEM
Tích hợp ESP32 Camera + YOLOv5 Detection + OCR
"""

import sys
import cv2
import os
import torch
import numpy as np
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QMessageBox, QStatusBar, QCheckBox, QSpinBox,
                             QGroupBox, QTextEdit)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont
import function.helper as helper
from collections import Counter, defaultdict
import threading
from queue import Queue

# ========== CONFIGURATION ==========
class Config:
    # Model paths
    DETECTOR_MODEL = "model/LP_detector_nano_61.pt"
    OCR_MODEL = "model/LP_ocr_nano_62.pt"
    
    # Detection settings
    DETECTOR_CONF = 0.3
    DETECTOR_IOU = 0.35
    OCR_CONF = 0.5
    
    # Zone settings
    ZONE_TOP = 0.25
    ZONE_BOTTOM = 0.75
    
    # OCR settings
    RESIZE_FACTOR = 2.5
    MIN_CONFIDENCE_CHARS = 7
    
    # Performance
    MAX_OCR_WORKERS = 2
    OCR_QUEUE_SIZE = 3


# ========== PREPROCESSING ==========
def preprocess_for_ocr(image, resize_factor=2.5, enable_preprocessing=True):
    """Tiền xử lý ảnh để tăng độ chính xác OCR"""
    if image is None or image.size == 0:
        return image
    
    h, w = image.shape[:2]
    
    # Resize lên để OCR chính xác hơn
    target_w = int(w * resize_factor)
    target_h = int(h * resize_factor)
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    
    if not enable_preprocessing:
        return resized
    
    # Denoise
    denoised = cv2.fastNlMeansDenoisingColored(resized, None, 10, 10, 7, 21)
    
    # Grayscale
    if len(denoised.shape) == 3:
        gray = cv2.cvtColor(denoised, cv2.COLOR_BGR2GRAY)
    else:
        gray = denoised
    
    # Sharpen
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(gray, -1, kernel)
    
    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(sharpened)
    
    # Convert back to BGR
    final = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    
    return final


# ========== ASYNC OCR PROCESSOR ==========
class AsyncOCRProcessor:
    """Xử lý OCR bất đồng bộ để không làm giảm FPS"""
    def __init__(self, ocr_model, max_workers=2):
        self.ocr_model = ocr_model
        self.task_queue = Queue(maxsize=Config.OCR_QUEUE_SIZE)
        self.result_queue = Queue()
        self.workers = []
        self.running = True
        
        for i in range(max_workers):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def _worker(self):
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.5)
                if task is None:
                    break
                
                frame_id, crop_img, bbox, enable_preprocess = task
                
                # Preprocess
                processed = preprocess_for_ocr(crop_img, enable_preprocessing=enable_preprocess)
                
                # OCR
                lp = helper.read_plate(self.ocr_model, processed)
                
                # Validate
                if lp != "unknown" and len(lp.replace("-", "")) >= Config.MIN_CONFIDENCE_CHARS:
                    self.result_queue.put((frame_id, lp, bbox))
                
                self.task_queue.task_done()
            except:
                continue
    
    def submit(self, frame_id, crop_img, bbox, enable_preprocess=True):
        try:
            self.task_queue.put_nowait((frame_id, crop_img, bbox, enable_preprocess))
            return True
        except:
            return False
    
    def get_results(self):
        results = []
        while not self.result_queue.empty():
            try:
                results.append(self.result_queue.get_nowait())
            except:
                break
        return results
    
    def stop(self):
        self.running = False
        for _ in self.workers:
            self.task_queue.put(None)
        for worker in self.workers:
            worker.join(timeout=2)


# ========== PLATE VOTING SYSTEM ==========
class PlateVotingSystem:
    """Hệ thống bỏ phiếu để chọn biển số chính xác nhất"""
    def __init__(self, window_size=15):
        self.window_size = window_size
        self.recent_plates = []
    
    def add(self, plate):
        self.recent_plates.append(plate)
        if len(self.recent_plates) > self.window_size:
            self.recent_plates.pop(0)
    
    def get_consensus(self, min_votes=3):
        if not self.recent_plates:
            return None
        
        counter = Counter(self.recent_plates)
        most_common = counter.most_common(1)[0]
        
        if most_common[1] >= min_votes:
            return most_common[0]
        return None
    
    def get_all_unique(self):
        return Counter(self.recent_plates)
    
    def clear(self):
        self.recent_plates.clear()


# ========== DETECTION THREAD ==========
class DetectionThread(QThread):
    """Thread xử lý detection và OCR"""
    frame_ready = pyqtSignal(object, list)  # (frame, detections)
    plate_detected = pyqtSignal(str, int)  # (plate_number, frame_id)
    stats_update = pyqtSignal(dict)  # Statistics
    
    def __init__(self, detector_model, ocr_model):
        super().__init__()
        self.detector = detector_model
        self.ocr_processor = AsyncOCRProcessor(ocr_model, max_workers=Config.MAX_OCR_WORKERS)
        self.voting_system = PlateVotingSystem(window_size=15)
        
        self.running = False
        self.current_frame = None
        self.frame_lock = threading.Lock()
        
        # Settings
        self.enable_zone = True
        self.enable_preprocessing = True
        self.zone_top = Config.ZONE_TOP
        self.zone_bottom = Config.ZONE_BOTTOM
        
        # Stats
        self.frame_count = 0
        self.plates_found = []
        self.display_results = {}
    
    def set_frame(self, frame):
        with self.frame_lock:
            self.current_frame = frame.copy() if frame is not None else None
    
    def run(self):
        self.running = True
        
        while self.running:
            with self.frame_lock:
                frame = self.current_frame
            
            if frame is None:
                self.msleep(10)
                continue
            
            self.frame_count += 1
            height, width = frame.shape[:2]
            
            # Calculate zone
            zone_top_y = int(height * self.zone_top)
            zone_bottom_y = int(height * self.zone_bottom)
            
            # Draw zone
            display_frame = frame.copy()
            if self.enable_zone:
                cv2.line(display_frame, (0, zone_top_y), (width, zone_top_y), (255, 0, 0), 2)
                cv2.line(display_frame, (0, zone_bottom_y), (width, zone_bottom_y), (0, 255, 0), 2)
                overlay = display_frame.copy()
                cv2.rectangle(overlay, (0, zone_top_y), (width, zone_bottom_y), (0, 255, 255), -1)
                cv2.addWeighted(overlay, 0.08, display_frame, 0.92, 0, display_frame)
            
            # Detect plates
            with torch.no_grad():
                plates = self.detector(frame, size=416)
                list_plates = plates.pandas().xyxy[0].values.tolist()
            
            detections = []
            
            # Process detections
            for plate in list_plates:
                x, y = int(plate[0]), int(plate[1])
                w = int(plate[2] - x)
                h = int(plate[3] - y)
                conf = plate[4]
                
                if w < 30 or h < 10:
                    continue
                
                center_y = y + h // 2
                
                # Check zone
                in_zone = True
                if self.enable_zone:
                    in_zone = zone_top_y <= center_y <= zone_bottom_y
                    if not in_zone:
                        cv2.rectangle(display_frame, (x, y), (x+w, y+h), (128, 128, 128), 1)
                        continue
                
                # Draw detection
                cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(display_frame, f"{conf:.2f}", (x, y-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # Crop with padding
                pad_x, pad_y = int(w * 0.15), int(h * 0.2)
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(width, x + w + pad_x)
                y2 = min(height, y + h + pad_y)
                
                crop_img = frame[y1:y2, x1:x2].copy()
                
                if crop_img.shape[0] >= 20 and crop_img.shape[1] >= 40:
                    self.ocr_processor.submit(self.frame_count, crop_img, (x, y, w, h), 
                                             self.enable_preprocessing)
                
                detections.append({
                    'bbox': (x, y, w, h),
                    'confidence': conf,
                    'in_zone': in_zone
                })
            
            # Get OCR results
            results = self.ocr_processor.get_results()
            
            for frame_id, lp, bbox in results:
                self.plates_found.append(lp)
                self.voting_system.add(lp)
                self.plate_detected.emit(lp, frame_id)
                
                if frame_id not in self.display_results:
                    self.display_results[frame_id] = []
                self.display_results[frame_id].append((bbox, lp))
            
            # Display OCR results
            for fid in list(self.display_results.keys()):
                if self.frame_count - fid > 20:
                    del self.display_results[fid]
                else:
                    for (x, y, w, h), lp in self.display_results[fid]:
                        # Draw background for text
                        text_size = cv2.getTextSize(lp, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
                        cv2.rectangle(display_frame, (x, y+h+5), (x+text_size[0]+10, y+h+30), 
                                    (0, 255, 0), -1)
                        cv2.putText(display_frame, lp, (x+5, y+h+25), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
            
            # Add info panel
            consensus = self.voting_system.get_consensus(min_votes=3)
            queue_size = self.ocr_processor.task_queue.qsize()
            
            # Emit frame and stats
            self.frame_ready.emit(display_frame, detections)
            self.stats_update.emit({
                'frame_count': self.frame_count,
                'queue_size': queue_size,
                'consensus': consensus,
                'total_plates': len(self.plates_found)
            })
            
            self.msleep(1)
    
    def stop(self):
        self.running = False
        self.ocr_processor.stop()
        self.wait()


# ========== CAMERA THREAD ==========
class CameraThread(QThread):
    """Thread để capture camera frames"""
    frame_ready = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)
    
    def __init__(self, stream_url):
        super().__init__()
        self.stream_url = stream_url
        self.running = False
        self.cap = None
    
    def run(self):
        self.running = True
        
        # Connect to stream
        self.cap = cv2.VideoCapture(self.stream_url)
        
        if not self.cap.isOpened():
            self.connection_status.emit(False, "Không thể kết nối camera")
            return
        
        self.connection_status.emit(True, "Đã kết nối camera")
        
        # Read frames
        while self.running:
            ret, frame = self.cap.read()
            
            if not ret:
                self.connection_status.emit(False, "Stream bị gián đoạn")
                break
            
            self.frame_ready.emit(frame)
        
        # Cleanup
        if self.cap:
            self.cap.release()
    
    def stop(self):
        self.running = False
        self.wait()


# ========== MAIN APPLICATION ==========
class LicensePlateRecognitionApp(QMainWindow):
    """Ứng dụng chính nhận diện biển số xe"""
    
    def __init__(self):
        super().__init__()
        
        # Settings
        self.esp32_ip = "192.168.1.148"
        self.stream_url = f"http://{self.esp32_ip}/stream"
        self.save_folder = "img"
        
        # Models
        self.detector_model = None
        self.ocr_model = None
        self.load_models()
        
        # Threads
        self.camera_thread = None
        self.detection_thread = None
        
        # State
        self.current_frame = None
        self.is_recording = False
        self.video_writer = None
        
        # FPS tracking
        self.frame_count = 0
        self.fps = 0.0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)
        
        # Setup UI
        self.init_ui()
        
        # Create save folder
        os.makedirs(self.save_folder, exist_ok=True)
    
    def load_models(self):
        """Load YOLOv5 models"""
        try:
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            print(f"🎯 Device: {device}")
            
            print("🔄 Đang tải models...")
            self.detector_model = torch.hub.load('ultralytics/yolov5', 'custom', 
                                                 path=Config.DETECTOR_MODEL, force_reload=False)
            self.detector_model.conf = Config.DETECTOR_CONF
            self.detector_model.iou = Config.DETECTOR_IOU
            
            self.ocr_model = torch.hub.load('ultralytics/yolov5', 'custom', 
                                           path=Config.OCR_MODEL, force_reload=False)
            self.ocr_model.conf = Config.OCR_CONF
            
            self.detector_model.to(device)
            self.ocr_model.to(device)
            print("✅ Models đã tải thành công!\n")
        except Exception as e:
            QMessageBox.critical(None, "Lỗi", f"Không thể tải models: {e}")
            sys.exit(1)
    
    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("🚗 Hệ Thống Nhận Diện Biển Số Xe")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Left panel - Video and controls
        left_panel = QVBoxLayout()
        
        # === CONNECTION CONTROLS ===
        conn_group = QGroupBox("Kết Nối Camera")
        conn_layout = QHBoxLayout()
        
        conn_layout.addWidget(QLabel("ESP32 IP:"))
        self.ip_input = QLineEdit(self.esp32_ip)
        self.ip_input.setMaximumWidth(150)
        conn_layout.addWidget(self.ip_input)
        
        self.connect_btn = QPushButton("Kết Nối")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)
        
        conn_group.setLayout(conn_layout)
        left_panel.addWidget(conn_group)
        
        # === DETECTION SETTINGS ===
        settings_group = QGroupBox("Cài Đặt Nhận Diện")
        settings_layout = QVBoxLayout()
        
        self.enable_zone_cb = QCheckBox("Bật vùng nhận diện")
        self.enable_zone_cb.setChecked(True)
        self.enable_zone_cb.stateChanged.connect(self.on_settings_changed)
        settings_layout.addWidget(self.enable_zone_cb)
        
        self.enable_preprocess_cb = QCheckBox("Bật tiền xử lý ảnh")
        self.enable_preprocess_cb.setChecked(True)
        self.enable_preprocess_cb.stateChanged.connect(self.on_settings_changed)
        settings_layout.addWidget(self.enable_preprocess_cb)
        
        settings_group.setLayout(settings_layout)
        left_panel.addWidget(settings_group)
        
        # === VIDEO DISPLAY ===
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #2b2b2b; color: white; font-size: 16px; border: 2px solid #333;")
        self.video_label.setMinimumSize(800, 600)
        self.video_label.setText("Nhấn 'Kết Nối' để bắt đầu")
        left_panel.addWidget(self.video_label)
        
        # === ACTION BUTTONS ===
        action_layout = QHBoxLayout()
        
        self.capture_btn = QPushButton("📸 Chụp Ảnh")
        self.capture_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px; font-size: 14px;")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self.capture_image)
        action_layout.addWidget(self.capture_btn)
        
        self.start_record_btn = QPushButton("🔴 Quay Video")
        self.start_record_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 10px; font-size: 14px;")
        self.start_record_btn.setEnabled(False)
        self.start_record_btn.clicked.connect(self.start_recording)
        action_layout.addWidget(self.start_record_btn)
        
        self.stop_record_btn = QPushButton("⏹️ Dừng Quay")
        self.stop_record_btn.setStyleSheet("background-color: #757575; color: white; font-weight: bold; padding: 10px; font-size: 14px;")
        self.stop_record_btn.setEnabled(False)
        self.stop_record_btn.clicked.connect(self.stop_recording)
        action_layout.addWidget(self.stop_record_btn)
        
        left_panel.addLayout(action_layout)
        
        # === STATS ===
        stats_layout = QHBoxLayout()
        
        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setFont(QFont("Arial", 10, QFont.Bold))
        stats_layout.addWidget(self.fps_label)
        
        self.frame_count_label = QLabel("Frames: 0")
        self.frame_count_label.setFont(QFont("Arial", 10))
        stats_layout.addWidget(self.frame_count_label)
        
        self.queue_label = QLabel("Queue: 0/5")
        self.queue_label.setFont(QFont("Arial", 10))
        stats_layout.addWidget(self.queue_label)
        
        stats_layout.addStretch()
        left_panel.addLayout(stats_layout)
        
        main_layout.addLayout(left_panel, 3)
        
        # === RIGHT PANEL - Results ===
        right_panel = QVBoxLayout()
        
        results_group = QGroupBox("Kết Quả Nhận Diện")
        results_layout = QVBoxLayout()
        
        self.consensus_label = QLabel("Biển số: ---")
        self.consensus_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.consensus_label.setStyleSheet("color: #4CAF50; padding: 10px; background-color: #1e1e1e; border-radius: 5px;")
        self.consensus_label.setAlignment(Qt.AlignCenter)
        results_layout.addWidget(self.consensus_label)
        
        results_layout.addWidget(QLabel("Lịch sử phát hiện:"))
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setMaximumHeight(300)
        self.history_text.setStyleSheet("background-color: #1e1e1e; color: white; font-family: 'Courier New';")
        results_layout.addWidget(self.history_text)
        
        results_layout.addWidget(QLabel("Thống kê:"))
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setStyleSheet("background-color: #1e1e1e; color: white; font-family: 'Courier New';")
        results_layout.addWidget(self.stats_text)
        
        results_group.setLayout(results_layout)
        right_panel.addWidget(results_group)
        
        main_layout.addLayout(right_panel, 1)
        
        # === STATUS BAR ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sẵn sàng")
    
    def toggle_connection(self):
        """Connect or disconnect"""
        if self.camera_thread and self.camera_thread.isRunning():
            self.disconnect_camera()
        else:
            self.connect_camera()
    
    def connect_camera(self):
        """Start camera and detection"""
        self.esp32_ip = self.ip_input.text().strip()
        self.stream_url = f"http://{self.esp32_ip}/stream"
        
        self.connect_btn.setEnabled(False)
        self.status_bar.showMessage(f"Đang kết nối {self.stream_url}...")
        
        # Start camera thread
        self.camera_thread = CameraThread(self.stream_url)
        self.camera_thread.frame_ready.connect(self.on_camera_frame)
        self.camera_thread.connection_status.connect(self.on_connection_status)
        self.camera_thread.start()
        
        # Start detection thread
        self.detection_thread = DetectionThread(self.detector_model, self.ocr_model)
        self.detection_thread.frame_ready.connect(self.update_frame)
        self.detection_thread.plate_detected.connect(self.on_plate_detected)
        self.detection_thread.stats_update.connect(self.on_stats_update)
        self.detection_thread.start()
        
        # Start FPS timer
        self.frame_count = 0
        self.fps_timer.start(1000)
    
    def disconnect_camera(self):
        """Stop camera and detection"""
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread = None
        
        if self.detection_thread:
            self.detection_thread.stop()
            self.detection_thread = None
        
        self.fps_timer.stop()
        
        # Stop recording
        if self.is_recording:
            self.stop_recording()
        
        # Update UI
        self.connect_btn.setText("Kết Nối")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.connect_btn.setEnabled(True)
        self.capture_btn.setEnabled(False)
        self.start_record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(False)
        
        self.video_label.setText("Đã ngắt kết nối")
        self.status_bar.showMessage("Đã ngắt kết nối")
    
    def on_connection_status(self, connected, message):
        """Handle connection status"""
        if connected:
            self.connect_btn.setText("Ngắt Kết Nối")
            self.connect_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
            self.connect_btn.setEnabled(True)
            self.capture_btn.setEnabled(True)
            self.start_record_btn.setEnabled(True)
            self.status_bar.showMessage(message)
        else:
            QMessageBox.warning(self, "Lỗi Kết Nối", message)
            self.disconnect_camera()
    
    def on_camera_frame(self, frame):
        """Receive frame from camera"""
        self.current_frame = frame
        self.frame_count += 1
        
        # Send to detection thread
        if self.detection_thread:
            self.detection_thread.set_frame(frame)
        
        # Write to video if recording
        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)
    
    def update_frame(self, frame, detections):
        """Update video display"""
        height, width, channels = frame.shape
        
        # Convert to QImage
        bytes_per_line = channels * width
        q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        
        # Scale to fit
        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.video_label.setPixmap(scaled_pixmap)
    
    def on_plate_detected(self, plate, frame_id):
        """Handle plate detection"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.history_text.append(f"[{timestamp}] Frame {frame_id}: {plate}")
    
    def on_stats_update(self, stats):
        """Update statistics"""
        self.frame_count_label.setText(f"Frames: {stats['frame_count']}")
        self.queue_label.setText(f"Queue: {stats['queue_size']}/{Config.OCR_QUEUE_SIZE}")
        
        if stats['consensus']:
            self.consensus_label.setText(f"Biển số: {stats['consensus']}")
        else:
            self.consensus_label.setText("Biển số: ---")
        
        # Update stats
        if self.detection_thread:
            plates = self.detection_thread.plates_found
            if plates:
                counter = Counter(plates)
                stats_text = f"Tổng phát hiện: {len(plates)}\n\n"
                stats_text += "Top 10 biển số:\n"
                for i, (plate, count) in enumerate(counter.most_common(10), 1):
                    percentage = (count / len(plates)) * 100
                    stats_text += f"{i}. {plate:15s} ({count:3d}x = {percentage:5.1f}%)\n"
                self.stats_text.setText(stats_text)
    
    def on_settings_changed(self):
        """Update detection settings"""
        if self.detection_thread:
            self.detection_thread.enable_zone = self.enable_zone_cb.isChecked()
            self.detection_thread.enable_preprocessing = self.enable_preprocess_cb.isChecked()
    
    def update_fps(self):
        """Update FPS display"""
        self.fps = self.frame_count
        self.fps_label.setText(f"FPS: {self.fps:.1f}")
        self.frame_count = 0
    
    def capture_image(self):
        """Save current frame"""
        if self.current_frame is None:
            QMessageBox.warning(self, "Lỗi", "Không có frame")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{timestamp}.jpg"
        filepath = os.path.join(self.save_folder, filename)
        
        success = cv2.imwrite(filepath, self.current_frame)
        
        if success:
            self.status_bar.showMessage(f"Đã lưu: {filepath}", 2000)
        else:
            QMessageBox.critical(self, "Lỗi", "Không thể lưu ảnh")
    
    def start_recording(self):
        """Start video recording"""
        if self.current_frame is None:
            QMessageBox.warning(self, "Lỗi", "Không có frame")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{timestamp}.avi"
        filepath = os.path.join(self.save_folder, filename)
        
        height, width, _ = self.current_frame.shape
        
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        self.video_writer = cv2.VideoWriter(filepath, fourcc, 20.0, (width, height))
        
        if not self.video_writer.isOpened():
            QMessageBox.critical(self, "Lỗi", "Không thể tạo file video")
            return
        
        self.is_recording = True
        self.start_record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)
        self.status_bar.showMessage(f"🔴 Đang quay: {filepath}")
    
    def stop_recording(self):
        """Stop video recording"""
        if not self.is_recording or not self.video_writer:
            return
        
        self.video_writer.release()
        self.video_writer = None
        self.is_recording = False
        
        self.start_record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)
        self.status_bar.showMessage("⏹️ Đã dừng quay", 3000)
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.is_recording:
            self.stop_recording()
        
        self.disconnect_camera()
        event.accept()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = LicensePlateRecognitionApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
