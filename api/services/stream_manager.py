"""
StreamManager — Manages video capture from various sources on a background thread.

Supported sources:
  - Webcam (integer device ID, e.g. "0", "1")
  - RTSP stream URL (rtsp://...)
  - HTTP MJPEG stream (e.g. ESP32-S3: http://192.168.4.1:81/stream)
  - Local video file (.mp4, .avi, etc.)

Provides:
  - latest raw frame (for API predict endpoints)
  - latest annotated frame (for MJPEG feed)
  - auto-reconnect on connection drop
"""
import threading
import time
from typing import Optional

import cv2
import numpy as np

from api.config import settings


class StreamManager:
    """
    Background video capture and processing manager.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._capture: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stream metadata
        self._source: str = ""
        self._mode: str = "lpr"
        self._active: bool = False
        self._frame_count: int = 0
        self._fps: float = 0.0
        self._width: int = 0
        self._height: int = 0

        # Frame buffers
        self._raw_frame: Optional[np.ndarray] = None
        self._annotated_frame: Optional[np.ndarray] = None

        # Reference to ALPRService (set via set_alpr_service)
        self._alpr_service = None

    def set_alpr_service(self, service) -> None:
        """Inject the ALPRService for processing frames."""
        self._alpr_service = service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, source: str, mode: str = "lpr") -> bool:
        """
        Start capturing from the given source.

        Args:
            source: Device ID (e.g. "0"), URL, or file path
            mode: "lpr" for full pipeline, "detect" for detection only

        Returns:
            True if capture opened successfully
        """
        # Stop any existing stream first
        if self._active:
            self.stop()

        # Parse source: if it's a plain integer string, convert to int (webcam)
        cap_source = int(source) if source.isdigit() else source

        cap = cv2.VideoCapture(cap_source)
        if not cap.isOpened():
            return False

        with self._lock:
            self._capture = cap
            self._source = source
            self._mode = mode
            self._frame_count = 0
            self._width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self._active = True

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the current stream and release resources."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            self._active = False
            self._raw_frame = None
            self._annotated_frame = None
            self._source = ""
            self._frame_count = 0

    @property
    def is_active(self) -> bool:
        return self._active

    def get_status(self) -> dict:
        """Return current stream status."""
        with self._lock:
            return {
                "active": self._active,
                "source": self._source,
                "mode": self._mode,
                "fps": round(self._fps, 1),
                "frame_count": self._frame_count,
                "resolution": {
                    "width": self._width,
                    "height": self._height,
                } if self._active else None,
            }

    def get_raw_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the latest raw frame."""
        with self._lock:
            if self._raw_frame is not None:
                return self._raw_frame.copy()
            return None

    def get_annotated_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the latest annotated (processed) frame."""
        with self._lock:
            if self._annotated_frame is not None:
                return self._annotated_frame.copy()
            return None

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Return latest frame (annotated if available, else raw). Used for snapshots."""
        with self._lock:
            frame = self._annotated_frame if self._annotated_frame is not None else self._raw_frame
            return frame.copy() if frame is not None else None


    # ------------------------------------------------------------------
    # MJPEG generator
    # ------------------------------------------------------------------

    def mjpeg_generator(self):
        """
        Yields MJPEG frames for StreamingResponse.
        Usage: StreamingResponse(manager.mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
        """
        interval = 1.0 / min(settings.stream_max_fps, 60)
        while self._active:
            frame = self.get_annotated_frame()
            if frame is not None:
                _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg.tobytes()
                    + b"\r\n"
                )
            time.sleep(interval)

    # ------------------------------------------------------------------
    # Background capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Runs on a background thread. Reads frames, processes them."""
        reconnect_delay = settings.stream_reconnect_delay

        while not self._stop_event.is_set():
            with self._lock:
                cap = self._capture
            if cap is None or not cap.isOpened():
                # Attempt reconnect
                time.sleep(reconnect_delay)
                cap_source = int(self._source) if self._source.isdigit() else self._source
                cap = cv2.VideoCapture(cap_source)
                if not cap.isOpened():
                    continue
                with self._lock:
                    self._capture = cap

            t0 = time.time()
            ret, frame = cap.read()

            if not ret or frame is None:
                # Connection dropped or end-of-file
                time.sleep(reconnect_delay)
                # Try to reopen
                with self._lock:
                    if self._capture is not None:
                        self._capture.release()
                    cap_source = int(self._source) if self._source.isdigit() else self._source
                    self._capture = cv2.VideoCapture(cap_source)
                continue

            # Store raw frame
            with self._lock:
                self._raw_frame = frame
                self._frame_count += 1

            # Process frame through ALPR if service available
            annotated = frame
            if self._alpr_service is not None and self._alpr_service.is_ready:
                try:
                    annotated, _, _ = self._alpr_service.process_and_extract(frame)
                except Exception:
                    annotated = frame

            with self._lock:
                self._annotated_frame = annotated
                dt = time.time() - t0
                self._fps = 1.0 / dt if dt > 0 else 0.0

        # Cleanup on exit
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            self._active = False
