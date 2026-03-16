"""PyQt5 tool to test ESP32-S3 camera stream + detector + OCR locally."""

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
from typing import List, Optional

import cv2
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

try:
    from backend.ml.detector import LicensePlateDetector
except Exception:
    LicensePlateDetector = None


APP_DIR = Path(__file__).resolve().parent
DEFAULT_STREAM_URL = os.getenv("ESP32_STREAM_URL", "http://192.168.1.8:81/stream")
DEFAULT_DETECTOR_MODEL_PATH = APP_DIR / "backend" / "ml" / "LP_detector_nano_61.pt"
DEFAULT_OCR_MODEL_PATH = APP_DIR / "backend" / "ml" / "LP_ocr_nano_62.pt"
SNAPSHOT_DIR = APP_DIR / "debug_snapshots"


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


class StreamWorker(QtCore.QThread):
    frame_ready = QtCore.pyqtSignal(object)
    stats_ready = QtCore.pyqtSignal(object)
    status_changed = QtCore.pyqtSignal(str)
    log_message = QtCore.pyqtSignal(str)
    model_state_changed = QtCore.pyqtSignal(str)
    plate_text_changed = QtCore.pyqtSignal(str)

    def __init__(
        self,
        stream_url: str,
        detector_model_path: str,
        ocr_model_path: str,
        confidence: float,
        detect_enabled: bool,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.stream_url = stream_url.strip()
        self._pending_detector_model_path = detector_model_path.strip()
        self._pending_ocr_model_path = ocr_model_path.strip()
        self._confidence = confidence
        self._detect_enabled = detect_enabled
        self._detector = None
        self._detector_model_path = ""
        self._ocr_model_path = ""
        self._model_device = "cpu"
        self._stop_event = Event()
        self._lock = Lock()
        self._frame_count = 0
        self._reconnect_count = 0
        self._fps = 0.0
        self._last_frame_at = time.monotonic()
        self._last_infer_at = 0.0
        self._last_boxes: List[DetectionBox] = []
        self._last_plate_text = ""
        self._infer_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="esp32-detect")
        self._infer_future: Optional[Future] = None
        self._last_infer_error = ""

    def stop(self) -> None:
        self._stop_event.set()

    def set_detection_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._detect_enabled = enabled

    def set_confidence(self, confidence: float) -> None:
        with self._lock:
            self._confidence = confidence

    def request_model_load(self, detector_model_path: str, ocr_model_path: str) -> None:
        with self._lock:
            self._pending_detector_model_path = detector_model_path.strip()
            self._pending_ocr_model_path = ocr_model_path.strip()

    def run(self) -> None:
        self.status_changed.emit("starting")
        self.log_message.emit(f"Worker start: {self.stream_url}")

        while not self._stop_event.is_set():
            self._load_pending_models_if_needed()
            cap = cv2.VideoCapture(self.stream_url)
            if not cap.isOpened():
                self.status_changed.emit("error")
                self.log_message.emit(f"Connect failed: {self.stream_url}")
                self._reconnect_count += 1
                self._sleep_before_retry()
                continue

            self.status_changed.emit("connected")
            self.log_message.emit("Connected to ESP32 stream")

            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.status_changed.emit("reconnecting")
                    self.log_message.emit("Stream interrupted, reconnecting...")
                    break

                output = self._process_frame(frame)
                self.frame_ready.emit(output)

            cap.release()

            if self._stop_event.is_set():
                break

            self._reconnect_count += 1
            self._sleep_before_retry()

        self._cancel_infer_job()
        self._infer_pool.shutdown(wait=False, cancel_futures=True)
        self.status_changed.emit("stopped")
        self.log_message.emit("Worker stopped")

    def _sleep_before_retry(self) -> None:
        delay_ms = min(1000 * max(1, self._reconnect_count), 5000)
        for _ in range(max(1, delay_ms // 100)):
            if self._stop_event.is_set():
                return
            self.msleep(100)

    def _load_pending_models_if_needed(self) -> None:
        detector_model_path = ""
        ocr_model_path = ""
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
            self.log_message.emit(f"Detector model not found: {detector_path}")
            return

        if not ocr_path.exists():
            self._detector = None
            self._detector_model_path = ""
            self._ocr_model_path = ""
            self._model_device = "cpu"
            self.model_state_changed.emit(f"OCR model not found: {ocr_path}")
            self.log_message.emit(f"OCR model not found: {ocr_path}")
            return

        if LicensePlateDetector is None:
            self._detector = None
            self._detector_model_path = ""
            self._ocr_model_path = ""
            self._model_device = "cpu"
            self.model_state_changed.emit("backend.ml.detector is not available")
            self.log_message.emit("backend.ml.detector is not available")
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
        self.log_message.emit(
            f"Models ready: detector={detector_path.name} | ocr={ocr_path.name} on {detector.device}"
        )

    def _process_frame(self, frame: np.ndarray) -> np.ndarray:
        self._frame_count += 1
        now = time.monotonic()
        delta = now - self._last_frame_at
        if delta > 0:
            self._fps = 1.0 / delta
        self._last_frame_at = now

        detect_enabled = False
        confidence = 0.35
        with self._lock:
            detect_enabled = self._detect_enabled
            confidence = self._confidence

        self._collect_infer_result()
        if detect_enabled and self._detector is not None and (now - self._last_infer_at) >= 0.20:
            self._maybe_schedule_infer(frame, confidence)
        elif not detect_enabled:
            self._cancel_infer_job()
            if self._last_boxes:
                self._last_boxes = []
            if self._last_plate_text:
                self._last_plate_text = ""
                self.plate_text_changed.emit("--")

        output = frame.copy()
        self._draw_overlay(output)
        self.stats_ready.emit(
            {
                "fps": self._fps,
                "frames": self._frame_count,
                "detections": len(self._last_boxes),
                "reconnects": self._reconnect_count,
                "device": self._model_device,
                "stream_url": self.stream_url,
                "detector_model": Path(self._detector_model_path).name if self._detector_model_path else "not loaded",
                "ocr_model": Path(self._ocr_model_path).name if self._ocr_model_path else "not loaded",
            }
        )
        return output

    def _maybe_schedule_infer(self, frame: np.ndarray, confidence: float) -> None:
        if self._infer_future and not self._infer_future.done():
            return
        self._last_infer_at = time.monotonic()
        self._infer_future = self._infer_pool.submit(self._infer, frame.copy(), confidence)

    def _collect_infer_result(self) -> None:
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

    def _cancel_infer_job(self) -> None:
        if self._infer_future and not self._infer_future.done():
            self._infer_future.cancel()
        self._infer_future = None

    def _infer(self, frame: np.ndarray, confidence: float) -> List[DetectionBox]:
        if self._detector is None:
            return []

        original_conf = self._detector.conf_threshold
        self._detector.conf_threshold = confidence
        try:
            results = self._detector.process_frame(frame)
        finally:
            self._detector.conf_threshold = original_conf

        detected: List[DetectionBox] = []
        for item in results:
            bbox = item.get("bbox") or {}
            x1 = int(bbox.get("x1", 0))
            y1 = int(bbox.get("y1", 0))
            x2 = int(bbox.get("x2", 0))
            y2 = int(bbox.get("y2", 0))
            plate_text = str(item.get("plate_text") or "").strip()
            score = float(item.get("overall_confidence") or item.get("detection_confidence") or 0.0)
            label = plate_text or "plate"
            detected.append(
                DetectionBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    label=label,
                    confidence=score,
                    plate_text=plate_text,
                )
            )
        return detected

    def _draw_overlay(self, frame: np.ndarray) -> None:
        for box in self._last_boxes:
            cv2.rectangle(frame, (box.x1, box.y1), (box.x2, box.y2), (0, 255, 0), 2)
            text = f"{box.label} {box.confidence:.2f}"
            cv2.putText(
                frame,
                text,
                (box.x1, max(20, box.y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        cv2.putText(
            frame,
            f"FPS {self._fps:.1f} | Frames {self._frame_count} | Det {len(self._last_boxes)}",
            (16, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (40, 220, 255),
            2,
            cv2.LINE_AA,
        )


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ESP32 Stream + Detector Tester")
        self.resize(1440, 920)
        self._worker: Optional[StreamWorker] = None
        self._last_frame: Optional[np.ndarray] = None
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        self._build_ui()
        self._log("Ready. Test stream + detect directly from ESP32.")

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        layout.addLayout(controls)

        self.stream_input = QtWidgets.QLineEdit(DEFAULT_STREAM_URL)
        self.detector_model_input = QtWidgets.QLineEdit(str(DEFAULT_DETECTOR_MODEL_PATH))
        self.ocr_model_input = QtWidgets.QLineEdit(str(DEFAULT_OCR_MODEL_PATH))
        self.conf_spin = QtWidgets.QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.35)
        self.detect_checkbox = QtWidgets.QCheckBox("Enable detect")
        self.detect_checkbox.setChecked(False)

        self.connect_button = QtWidgets.QPushButton("Connect stream")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.load_models_button = QtWidgets.QPushButton("Load models")
        self.snapshot_button = QtWidgets.QPushButton("Save snapshot")
        self.detector_browse_button = QtWidgets.QPushButton("Browse")
        self.ocr_browse_button = QtWidgets.QPushButton("Browse")

        controls.addWidget(QtWidgets.QLabel("ESP32 stream URL"), 0, 0)
        controls.addWidget(self.stream_input, 0, 1, 1, 5)
        controls.addWidget(self.connect_button, 0, 6)
        controls.addWidget(self.stop_button, 0, 7)

        controls.addWidget(QtWidgets.QLabel("Detector model"), 1, 0)
        controls.addWidget(self.detector_model_input, 1, 1, 1, 4)
        controls.addWidget(self.detector_browse_button, 1, 5)
        controls.addWidget(self.load_models_button, 1, 6)
        controls.addWidget(self.snapshot_button, 1, 7)

        controls.addWidget(QtWidgets.QLabel("OCR model"), 2, 0)
        controls.addWidget(self.ocr_model_input, 2, 1, 1, 4)
        controls.addWidget(self.ocr_browse_button, 2, 5)

        controls.addWidget(QtWidgets.QLabel("Confidence"), 3, 0)
        controls.addWidget(self.conf_spin, 3, 1)
        controls.addWidget(self.detect_checkbox, 3, 2)

        body = QtWidgets.QHBoxLayout()
        layout.addLayout(body, stretch=1)

        self.video_label = QtWidgets.QLabel("No frame")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setMinimumSize(960, 540)
        self.video_label.setStyleSheet("background:#111; color:#ddd; border:1px solid #333;")
        body.addWidget(self.video_label, stretch=3)

        side = QtWidgets.QVBoxLayout()
        body.addLayout(side, stretch=2)

        self.status_label = QtWidgets.QLabel("Status: idle")
        self.model_state_label = QtWidgets.QLabel("Models: not loaded")
        self.stats_label = QtWidgets.QLabel("Frames: 0 | FPS: 0.0 | Detections: 0")
        self.stream_label = QtWidgets.QLabel("Stream: -")
        self.plate_label = QtWidgets.QLabel("Plate OCR: --")

        for widget in (self.status_label, self.model_state_label, self.stats_label, self.stream_label, self.plate_label):
            widget.setWordWrap(True)
            side.addWidget(widget)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(400)
        side.addWidget(self.log_box, stretch=1)

        self.connect_button.clicked.connect(self.start_stream)
        self.stop_button.clicked.connect(self.stop_stream)
        self.load_models_button.clicked.connect(self.load_models)
        self.snapshot_button.clicked.connect(self.save_snapshot)
        self.detector_browse_button.clicked.connect(self.browse_detector_model)
        self.ocr_browse_button.clicked.connect(self.browse_ocr_model)
        self.detect_checkbox.toggled.connect(self.on_detection_toggled)
        self.conf_spin.valueChanged.connect(self.on_confidence_changed)

    def browse_detector_model(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select detector model",
            str(DEFAULT_DETECTOR_MODEL_PATH.parent),
            "Model (*.pt *.onnx);;All files (*.*)",
        )
        if path:
            self.detector_model_input.setText(path)

    def browse_ocr_model(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select OCR model",
            str(DEFAULT_OCR_MODEL_PATH.parent),
            "Model (*.pt *.onnx);;All files (*.*)",
        )
        if path:
            self.ocr_model_input.setText(path)

    def start_stream(self) -> None:
        if self._worker and self._worker.isRunning():
            self._log("Stream already running")
            return

        stream_url = self.stream_input.text().strip()
        detector_path = self.detector_model_input.text().strip()
        ocr_path = self.ocr_model_input.text().strip()
        if not stream_url:
            self._log("Please enter ESP32 stream URL")
            return

        self._worker = StreamWorker(
            stream_url=stream_url,
            detector_model_path=detector_path,
            ocr_model_path=ocr_path,
            confidence=float(self.conf_spin.value()),
            detect_enabled=self.detect_checkbox.isChecked(),
        )
        self._worker.frame_ready.connect(self.on_frame_ready)
        self._worker.stats_ready.connect(self.on_stats_ready)
        self._worker.status_changed.connect(self.on_status_changed)
        self._worker.log_message.connect(self._log)
        self._worker.model_state_changed.connect(self.on_model_state_changed)
        self._worker.plate_text_changed.connect(self.on_plate_text_changed)
        self._worker.start()
        self._log("Start stream test")

    def stop_stream(self) -> None:
        if not self._worker:
            return
        self._worker.stop()
        self._worker.wait(4000)
        self._worker = None
        self.status_label.setText("Status: stopped")

    def load_models(self) -> None:
        if not self._worker or not self._worker.isRunning():
            self._log("Start stream first, then load models")
            return

        detector_path = self.detector_model_input.text().strip()
        ocr_path = self.ocr_model_input.text().strip()
        self._worker.request_model_load(detector_path, ocr_path)
        self._log(
            f"Queued models: detector={Path(detector_path).name} | ocr={Path(ocr_path).name}"
        )

    def save_snapshot(self) -> None:
        if self._last_frame is None:
            self._log("No frame available to save")
            return
        file_path = SNAPSHOT_DIR / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(str(file_path), self._last_frame)
        self._log(f"Saved snapshot: {file_path}")

    def on_detection_toggled(self, checked: bool) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.set_detection_enabled(checked)
        self._log(f"Detection {'enabled' if checked else 'disabled'}")

    def on_confidence_changed(self, value: float) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.set_confidence(float(value))

    def on_frame_ready(self, frame: np.ndarray) -> None:
        self._last_frame = frame.copy()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.video_label.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)

    def on_stats_ready(self, stats: dict) -> None:
        self.stats_label.setText(
            "Frames: {frames} | FPS: {fps:.1f} | Detections: {detections} | Reconnects: {reconnects}".format(
                **stats
            )
        )
        self.stream_label.setText(
            "Stream: {stream} | Device: {device} | Detector: {detector} | OCR: {ocr}".format(
                stream=stats["stream_url"],
                device=stats["device"],
                detector=stats["detector_model"],
                ocr=stats["ocr_model"],
            )
        )

    def on_status_changed(self, status: str) -> None:
        self.status_label.setText(f"Status: {status}")

    def on_model_state_changed(self, state: str) -> None:
        self.model_state_label.setText(f"Models: {state}")

    def on_plate_text_changed(self, plate_text: str) -> None:
        self.plate_label.setText(f"Plate OCR: {plate_text or '--'}")

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.appendPlainText(f"[{timestamp}] {message}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.stop_stream()
        super().closeEvent(event)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("ESP32 Stream + Detector Tester")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
