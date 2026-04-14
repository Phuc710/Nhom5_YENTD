"""
Stream Client — Kéo MJPEG stream từ ESP32 trong QThread riêng.
Tự động reconnect khi mất kết nối.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

logger = logging.getLogger(__name__)

RECONNECT_DELAY_S = 3.0
READ_TIMEOUT_S    = 5.0


class StreamClientThread(QThread):
    """
    Kết nối đến MJPEG endpoint của ESP32, decode frame và emit signal.
    Tự động retry khi mất kết nối.
    """

    frame_ready    = pyqtSignal(QImage, np.ndarray)  # (qt_img_for_display, np_frame_for_AI)
    stream_status  = pyqtSignal(bool, str)            # (connected, message)

    def __init__(self, stream_url: str = "", camera_id: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.stream_url  = stream_url
        self.camera_id   = camera_id
        self._running    = False
        self._cap: Optional[cv2.VideoCapture] = None

    # ── QThread entry ──────────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        while self._running:
            if not self.stream_url:
                time.sleep(1.0)
                continue
            self._connect_and_stream()
            if self._running:
                logger.warning("[Stream] Reconnecting in %.1fs ...", RECONNECT_DELAY_S)
                self.stream_status.emit(False, "Đang kết nối lại...")
                time.sleep(RECONNECT_DELAY_S)

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()

    def set_url(self, url: str) -> None:
        """Đổi URL stream (sẽ tự reconnect)."""
        self.stream_url = url
        if self._cap:
            self._cap.release()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _connect_and_stream(self) -> None:
        # Nếu stream_url là chuỗi số (ví dụ "0", "1") -> chuyển thành int để mở webcam
        target = self.stream_url
        if isinstance(target, str) and target.isdigit():
            target = int(target)

        logger.info("[Stream] Connecting to: %s", target)
        self.stream_status.emit(False, f"Đang kết nối {target} ...")

        cap = cv2.VideoCapture(target)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(READ_TIMEOUT_S * 1000))
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(READ_TIMEOUT_S * 1000))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap

        if not cap.isOpened():
            logger.warning("[Stream] Cannot open %s", self.stream_url)
            self.stream_status.emit(False, f"Không mở được stream: {self.stream_url}")
            return

        # Phát hiện nếu là file video local (mp4, avi,..): loop lại khi hết
        import os
        _VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".m4v", ".ts"}
        is_local_file = (
            not self.stream_url.startswith("http")
            and os.path.isfile(self.stream_url)
            and os.path.splitext(self.stream_url)[1].lower() in _VIDEO_EXTS
        )

        logger.info("[Stream] Connected ✅ %s", "(local file — loop mode)" if is_local_file else "")
        self.stream_status.emit(True, "Stream đang chạy")

        while self._running:
            try:
                ok, frame = cap.read()
            except Exception as e:
                logger.warning("[Stream] OpenCV exception during cap.read(): %s", e)
                break

            if not ok or frame is None:
                if is_local_file:
                    # Hết video → loop lại từ đầu
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.warning("[Stream] Frame read failed — disconnected")
                    break

            try:
                self._emit_frame(frame)
            except Exception as exc:
                logger.debug("[Stream] emit frame error: %s", exc)

        cap.release()
        self._cap = None
        self.stream_status.emit(False, "Mất kết nối stream")

    def _emit_frame(self, frame: np.ndarray) -> None:
        """Convert OpenCV BGR → QImage và emit cùng raw numpy frame."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        self.frame_ready.emit(qt_img, frame.copy())
