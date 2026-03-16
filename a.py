"""
ESP32-S3 Camera Viewer - PyQt5 GUI
Displays live camera stream with snapshot, recording, and plate detection support.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Optional

import cv2
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

try:
    from backend.ml.detector import LicensePlateDetector
except Exception:
    LicensePlateDetector = None


APP_DIR = Path(__file__).resolve().parent
DEFAULT_STREAM_HOST = "192.168.1.8:81"
DEFAULT_DETECTOR_MODEL_PATH = APP_DIR / "backend" / "ml" / "LP_detector_nano_61.pt"
DEFAULT_OCR_MODEL_PATH = APP_DIR / "backend" / "ml" / "LP_ocr_nano_62.pt"


@contextlib.contextmanager
def _suppress_noisy_output():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


@dataclass
class DetectionBox:
    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    confidence: float
    plate_text: str = ""


class CameraThread(QThread):
    """Thread for capturing camera frames and running detector in the background."""

    frame_ready = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)
    stats_ready = pyqtSignal(dict)
    model_state_changed = pyqtSignal(str)
    plate_text_changed = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(
        self,
        stream_url: str,
        detector_model_path: str,
        ocr_model_path: str,
        confidence: float,
        detect_enabled: bool,
        rotation_degrees: int,
    ):
        super().__init__()
        self.stream_url = stream_url
        self.running = False
        self.cap = None

        self._pending_detector_model_path = detector_model_path.strip()
        self._pending_ocr_model_path = ocr_model_path.strip()
        self._confidence = confidence
        self._detect_enabled = detect_enabled
        self._rotation_degrees = rotation_degrees
        self._detector = None
        self._detector_model_path = ""
        self._ocr_model_path = ""
        self._model_device = "cpu"
        self._lock = Lock()
        self._stop_event = Event()

        self._frame_counter = 0
        self._session_frames = 0
        self._fps = 0.0
        self._last_frame_at = time.monotonic()
        self._last_infer_at = 0.0
        self._reconnects = 0

        self._last_boxes: list[DetectionBox] = []
        self._last_plate_text = ""
        self._last_infer_error = ""
        self._infer_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="a-detect")
        self._infer_future: Optional[Future] = None

    def run(self):
        self.running = True
        self.log_message.emit(f"Worker start: {self.stream_url}")

        while self.running and not self._stop_event.is_set():
            self._load_pending_models_if_needed()

            self.cap = cv2.VideoCapture(self.stream_url)
            if not self.cap.isOpened():
                self.connection_status.emit(False, "Failed to connect to camera")
                self._reconnects += 1
                self._sleep_before_retry()
                continue

            self.connection_status.emit(True, "Connected to camera")

            while self.running and not self._stop_event.is_set():
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    self.connection_status.emit(False, "Stream interrupted")
                    self._reconnects += 1
                    break

                frame = self._apply_orientation(frame)
                output = self._process_frame(frame)
                self.frame_ready.emit(output)

            if self.cap:
                self.cap.release()
                self.cap = None

            if self.running and not self._stop_event.is_set():
                self._sleep_before_retry()

        self._cancel_infer_job()
        self._infer_pool.shutdown(wait=False, cancel_futures=True)
        if self.cap:
            self.cap.release()
            self.cap = None
        self.log_message.emit("Worker stopped")

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._cancel_infer_job()
        self.wait(4000)

    def set_detection_enabled(self, enabled: bool):
        with self._lock:
            self._detect_enabled = enabled

    def set_confidence(self, confidence: float):
        with self._lock:
            self._confidence = confidence

    def request_model_load(self, detector_model_path: str, ocr_model_path: str):
        with self._lock:
            self._pending_detector_model_path = detector_model_path.strip()
            self._pending_ocr_model_path = ocr_model_path.strip()

    def set_rotation(self, rotation_degrees: int):
        with self._lock:
            self._rotation_degrees = rotation_degrees

    def _sleep_before_retry(self):
        delay_ms = min(1000 * max(1, self._reconnects), 5000)
        for _ in range(max(1, delay_ms // 100)):
            if self._stop_event.is_set():
                return
            self.msleep(100)

    def _load_pending_models_if_needed(self):
        with self._lock:
            detector_model_path = self._pending_detector_model_path
            ocr_model_path = self._pending_ocr_model_path
            self._pending_detector_model_path = ""
            self._pending_ocr_model_path = ""

        if not detector_model_path and not ocr_model_path:
            return

        detector_path = Path(detector_model_path or self._detector_model_path or DEFAULT_DETECTOR_MODEL_PATH)
        ocr_path = Path(ocr_model_path or self._ocr_model_path or DEFAULT_OCR_MODEL_PATH)

        self._cancel_infer_job()
        self._last_boxes = []
        self._last_plate_text = ""
        self.plate_text_changed.emit("--")

        if not detector_path.exists():
            self._detector = None
            self._detector_model_path = ""
            self._ocr_model_path = ""
            self._model_device = "cpu"
            self.model_state_changed.emit(f"Detector model not found: {detector_path}")
            return

        if not ocr_path.exists():
            self._detector = None
            self._detector_model_path = ""
            self._ocr_model_path = ""
            self._model_device = "cpu"
            self.model_state_changed.emit(f"OCR model not found: {ocr_path}")
            return

        if LicensePlateDetector is None:
            self._detector = None
            self._detector_model_path = ""
            self._ocr_model_path = ""
            self._model_device = "cpu"
            self.model_state_changed.emit("backend.ml.detector is not available")
            return

        self.model_state_changed.emit("Loading detector + OCR...")
        self.log_message.emit(f"Loading detector: {detector_path}")
        self.log_message.emit(f"Loading OCR: {ocr_path}")

        with _suppress_noisy_output():
            detector = LicensePlateDetector(
                detector_model_path=str(detector_path),
                ocr_model_path=str(ocr_path),
            )

        self._detector = detector
        self._detector_model_path = str(detector_path)
        self._ocr_model_path = str(ocr_path)
        self._model_device = detector.device
        self._last_infer_error = ""
        self.model_state_changed.emit(
            f"Loaded detector={detector_path.name} | ocr={ocr_path.name} on {detector.device}"
        )
        self.log_message.emit("Models ready")

    def _process_frame(self, frame):
        self._frame_counter += 1
        self._session_frames += 1

        now = time.monotonic()
        delta = now - self._last_frame_at
        if delta > 0:
            self._fps = 1.0 / delta
        self._last_frame_at = now

        with self._lock:
            detect_enabled = self._detect_enabled
            confidence = self._confidence

        self._collect_infer_result()
        if detect_enabled and self._detector is not None and (now - self._last_infer_at) >= 0.20:
            self._maybe_schedule_infer(frame, confidence)
        elif not detect_enabled:
            self._cancel_infer_job()
            self._last_boxes = []
            if self._last_plate_text:
                self._last_plate_text = ""
                self.plate_text_changed.emit("--")

        output = frame.copy()
        self._draw_overlay(output)
        self.stats_ready.emit(
            {
                "fps": self._fps,
                "frames": self._session_frames,
                "width": output.shape[1],
                "height": output.shape[0],
                "detections": len(self._last_boxes),
                "reconnects": self._reconnects,
                "device": self._model_device,
            }
        )
        return output

    def _apply_orientation(self, frame):
        with self._lock:
            rotation_degrees = self._rotation_degrees

        if rotation_degrees == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if rotation_degrees == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        if rotation_degrees == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _maybe_schedule_infer(self, frame, confidence: float):
        if self._infer_future and not self._infer_future.done():
            return
        self._last_infer_at = time.monotonic()
        self._infer_future = self._infer_pool.submit(self._infer, frame.copy(), confidence)

    def _collect_infer_result(self):
        if not self._infer_future or not self._infer_future.done():
            return

        future = self._infer_future
        self._infer_future = None
        try:
            self._last_boxes = future.result()
            self._last_infer_error = ""
            best_text = next((box.plate_text for box in self._last_boxes if box.plate_text), "")
            if best_text != self._last_plate_text:
                self._last_plate_text = best_text
                self.plate_text_changed.emit(best_text or "--")
        except Exception as exc:
            message = str(exc)
            if message != self._last_infer_error:
                self._last_infer_error = message
                self.log_message.emit(f"Detect failed: {message}")
            self._last_boxes = []
            if self._last_plate_text:
                self._last_plate_text = ""
                self.plate_text_changed.emit("--")

    def _cancel_infer_job(self):
        if self._infer_future and not self._infer_future.done():
            self._infer_future.cancel()
        self._infer_future = None

    def _infer(self, frame, confidence: float) -> list[DetectionBox]:
        if self._detector is None:
            return []

        original_conf = self._detector.conf_threshold
        self._detector.conf_threshold = confidence
        try:
            results = self._detector.process_frame(frame)
        finally:
            self._detector.conf_threshold = original_conf

        boxes: list[DetectionBox] = []
        for item in results:
            bbox = item.get("bbox") or {}
            plate_text = str(item.get("plate_text") or "").strip()
            label = plate_text or "plate"
            score = float(item.get("overall_confidence") or item.get("detection_confidence") or 0.0)
            boxes.append(
                DetectionBox(
                    x1=int(bbox.get("x1", 0)),
                    y1=int(bbox.get("y1", 0)),
                    x2=int(bbox.get("x2", 0)),
                    y2=int(bbox.get("y2", 0)),
                    label=label,
                    confidence=score,
                    plate_text=plate_text,
                )
            )
        return boxes

    def _draw_overlay(self, frame):
        for box in self._last_boxes:
            cv2.rectangle(frame, (box.x1, box.y1), (box.x2, box.y2), (0, 255, 0), 2)
            cv2.putText(
                frame,
                f"{box.label} {box.confidence:.2f}",
                (box.x1, max(20, box.y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )


class CameraViewer(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.esp32_ip = DEFAULT_STREAM_HOST
        self.stream_url = f"http://{self.esp32_ip}/stream"
        self.save_folder = "img"

        self.camera_thread: Optional[CameraThread] = None
        self.current_frame = None
        self.frame_count = 0
        self.fps = 0.0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)

        self.is_recording = False
        self.video_writer = None
        self.recording_start_time = None

        self.init_ui()
        os.makedirs(self.save_folder, exist_ok=True)

    def init_ui(self):
        self.setWindowTitle("ESP32-S3 Camera Viewer + Detect")
        self.setGeometry(100, 100, 1200, 840)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        controls_grid = QGridLayout()
        controls_grid.setHorizontalSpacing(10)
        controls_grid.setVerticalSpacing(8)

        ip_label = QLabel("ESP32 IP:")
        ip_label.setFont(QFont("Arial", 10, QFont.Bold))
        controls_grid.addWidget(ip_label, 0, 0)

        self.ip_input = QLineEdit(self.esp32_ip)
        controls_grid.addWidget(self.ip_input, 0, 1)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.connect_btn.clicked.connect(self.toggle_connection)
        controls_grid.addWidget(self.connect_btn, 0, 2)

        self.detect_checkbox = QCheckBox("Enable detect")
        controls_grid.addWidget(self.detect_checkbox, 0, 3)

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.35)
        controls_grid.addWidget(self.conf_spin, 0, 4)

        self.rotation_combo = QComboBox()
        self.rotation_combo.addItem("Rotate 0", 0)
        self.rotation_combo.addItem("Rotate 90", 90)
        self.rotation_combo.addItem("Rotate 180", 180)
        self.rotation_combo.addItem("Rotate 270", 270)
        self.rotation_combo.setCurrentIndex(2)
        controls_grid.addWidget(self.rotation_combo, 0, 5)

        self.load_models_btn = QPushButton("Load models")
        self.load_models_btn.clicked.connect(self.load_models)
        controls_grid.addWidget(self.load_models_btn, 0, 6)

        self.capture_btn = QPushButton("Capture")
        self.capture_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self.capture_image)
        controls_grid.addWidget(self.capture_btn, 0, 7)

        self.start_record_btn = QPushButton("Start Recording")
        self.start_record_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
        self.start_record_btn.setEnabled(False)
        self.start_record_btn.clicked.connect(self.start_recording)
        controls_grid.addWidget(self.start_record_btn, 0, 8)

        self.stop_record_btn = QPushButton("Stop Recording")
        self.stop_record_btn.setStyleSheet("background-color: #757575; color: white; font-weight: bold; padding: 8px;")
        self.stop_record_btn.setEnabled(False)
        self.stop_record_btn.clicked.connect(self.stop_recording)
        controls_grid.addWidget(self.stop_record_btn, 0, 9)

        controls_grid.addWidget(QLabel("Detector model:"), 1, 0)
        self.detector_model_input = QLineEdit(str(DEFAULT_DETECTOR_MODEL_PATH))
        controls_grid.addWidget(self.detector_model_input, 1, 1, 1, 4)
        detector_browse_btn = QPushButton("Browse")
        detector_browse_btn.clicked.connect(self.browse_detector_model)
        controls_grid.addWidget(detector_browse_btn, 1, 5)

        controls_grid.addWidget(QLabel("OCR model:"), 2, 0)
        self.ocr_model_input = QLineEdit(str(DEFAULT_OCR_MODEL_PATH))
        controls_grid.addWidget(self.ocr_model_input, 2, 1, 1, 4)
        ocr_browse_btn = QPushButton("Browse")
        ocr_browse_btn.clicked.connect(self.browse_ocr_model)
        controls_grid.addWidget(ocr_browse_btn, 2, 5)

        main_layout.addLayout(controls_grid)

        body_layout = QHBoxLayout()
        main_layout.addLayout(body_layout, stretch=1)

        self.video_label = QLabel("Click 'Connect' to start stream")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(760, 520)
        self.video_label.setStyleSheet("background-color: #111; color: white; font-size: 16px; border: 2px solid #333;")
        body_layout.addWidget(self.video_label, stretch=3)

        side_layout = QVBoxLayout()
        body_layout.addLayout(side_layout, stretch=2)

        self.model_state_label = QLabel("Models: not loaded")
        self.model_state_label.setWordWrap(True)
        side_layout.addWidget(self.model_state_label)

        self.plate_label = QLabel("Plate OCR: --")
        self.plate_label.setWordWrap(True)
        side_layout.addWidget(self.plate_label)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(300)
        side_layout.addWidget(self.log_box, stretch=1)

        info_layout = QHBoxLayout()
        self.fps_label = QLabel("FPS: 0.0")
        self.resolution_label = QLabel("Resolution: N/A")
        self.frame_count_label = QLabel("Frames: 0")
        self.detection_label = QLabel("Detections: 0")
        info_layout.addWidget(self.fps_label)
        info_layout.addWidget(self.resolution_label)
        info_layout.addWidget(self.frame_count_label)
        info_layout.addWidget(self.detection_label)
        info_layout.addStretch()
        main_layout.addLayout(info_layout)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.detect_checkbox.toggled.connect(self.on_detection_toggled)
        self.conf_spin.valueChanged.connect(self.on_confidence_changed)
        self.rotation_combo.currentIndexChanged.connect(self.on_rotation_changed)

    def browse_detector_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select detector model",
            str(DEFAULT_DETECTOR_MODEL_PATH.parent),
            "Model (*.pt *.onnx);;All files (*.*)",
        )
        if path:
            self.detector_model_input.setText(path)

    def browse_ocr_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OCR model",
            str(DEFAULT_OCR_MODEL_PATH.parent),
            "Model (*.pt *.onnx);;All files (*.*)",
        )
        if path:
            self.ocr_model_input.setText(path)

    def toggle_connection(self):
        if self.camera_thread and self.camera_thread.isRunning():
            self.disconnect_camera()
        else:
            self.connect_camera()

    def connect_camera(self):
        self.esp32_ip = self.ip_input.text().strip()
        self.stream_url = f"http://{self.esp32_ip}/stream"

        self.connect_btn.setEnabled(False)
        self.status_bar.showMessage(f"Connecting to {self.stream_url}...")
        self.frame_count = 0
        self.video_label.setProperty("total_frames", 0)

        self.camera_thread = CameraThread(
            stream_url=self.stream_url,
            detector_model_path=self.detector_model_input.text().strip(),
            ocr_model_path=self.ocr_model_input.text().strip(),
            confidence=float(self.conf_spin.value()),
            detect_enabled=self.detect_checkbox.isChecked(),
            rotation_degrees=int(self.rotation_combo.currentData()),
        )
        self.camera_thread.frame_ready.connect(self.update_frame)
        self.camera_thread.connection_status.connect(self.on_connection_status)
        self.camera_thread.stats_ready.connect(self.on_stats_ready)
        self.camera_thread.model_state_changed.connect(self.on_model_state_changed)
        self.camera_thread.plate_text_changed.connect(self.on_plate_text_changed)
        self.camera_thread.log_message.connect(self._log)
        self.camera_thread.start()

        self.fps_timer.start(1000)

    def disconnect_camera(self):
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread = None

        self.fps_timer.stop()

        if self.is_recording:
            self.stop_recording()

        self.connect_btn.setText("Connect")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.connect_btn.setEnabled(True)
        self.capture_btn.setEnabled(False)
        self.start_record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(False)
        self.video_label.setText("Disconnected")
        self.video_label.setPixmap(QPixmap())
        self.status_bar.showMessage("Disconnected")

    def load_models(self):
        if not self.camera_thread or not self.camera_thread.isRunning():
            self._log("Start stream first, then load models")
            return
        self.camera_thread.request_model_load(
            self.detector_model_input.text().strip(),
            self.ocr_model_input.text().strip(),
        )
        self._log("Queued model reload")

    def on_detection_toggled(self, checked: bool):
        if self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.set_detection_enabled(checked)
        self._log(f"Detection {'enabled' if checked else 'disabled'}")

    def on_confidence_changed(self, value: float):
        if self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.set_confidence(float(value))

    def on_rotation_changed(self, _index: int):
        rotation_degrees = int(self.rotation_combo.currentData() or 0)
        if self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.set_rotation(rotation_degrees)
        self._log(f"Rotation set to {rotation_degrees}")

    def on_connection_status(self, connected: bool, message: str):
        if connected:
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
            self.connect_btn.setEnabled(True)
            self.capture_btn.setEnabled(True)
            self.start_record_btn.setEnabled(True)
            self.status_bar.showMessage(message)
        else:
            self.status_bar.showMessage(message)
            if self.camera_thread and self.camera_thread.running:
                self._log(message)

    def on_stats_ready(self, stats: dict):
        self.resolution_label.setText(f"Resolution: {stats['width']}x{stats['height']}")
        self.detection_label.setText(f"Detections: {stats['detections']}")
        self.frame_count_label.setText(f"Frames: {stats['frames']}")

    def on_model_state_changed(self, state: str):
        self.model_state_label.setText(f"Models: {state}")

    def on_plate_text_changed(self, plate_text: str):
        self.plate_label.setText(f"Plate OCR: {plate_text or '--'}")

    def update_frame(self, frame):
        self.current_frame = frame.copy()
        self.frame_count += 1

        total_frames = int(self.video_label.property("total_frames") or 0) + 1
        self.video_label.setProperty("total_frames", total_frames)

        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

        height, width, channels = frame.shape
        bytes_per_line = channels * width
        q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setPixmap(scaled_pixmap)

    def update_fps(self):
        self.fps = self.frame_count
        self.fps_label.setText(f"FPS: {self.fps:.1f}")
        self.frame_count = 0

    def capture_image(self):
        if self.current_frame is None:
            QMessageBox.warning(self, "Capture Error", "No frame available")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.save_folder, f"capture_{timestamp}.jpg")
        success = cv2.imwrite(filepath, self.current_frame)
        if success:
            self.status_bar.showMessage(f"Saved: {filepath}", 2000)
        else:
            QMessageBox.critical(self, "Capture Error", "Failed to save image")

    def start_recording(self):
        if self.current_frame is None:
            QMessageBox.warning(self, "Recording Error", "No frame available")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.save_folder, f"video_{timestamp}.avi")
        height, width, _ = self.current_frame.shape
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        self.video_writer = cv2.VideoWriter(filepath, fourcc, 20.0, (width, height))

        if not self.video_writer.isOpened():
            QMessageBox.critical(self, "Recording Error", "Failed to create video file")
            return

        self.is_recording = True
        self.recording_start_time = datetime.now()
        self.start_record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)
        self.status_bar.showMessage(f"Recording: {filepath}")

    def stop_recording(self):
        if not self.is_recording or not self.video_writer:
            return

        self.video_writer.release()
        self.video_writer = None
        self.is_recording = False

        if self.recording_start_time:
            duration = (datetime.now() - self.recording_start_time).total_seconds()
            self.status_bar.showMessage(f"Recording stopped ({duration:.1f}s)", 3000)

        self.start_record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.appendPlainText(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        if self.is_recording:
            self.stop_recording()
        self.disconnect_camera()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    viewer = CameraViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
