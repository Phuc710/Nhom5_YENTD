"""
ALPRService — Thread-safe singleton that wraps ALPRCore.

Responsibilities:
  - Initialize ALPRCore once at startup
  - Provide `process_and_extract()` which returns BOTH
    the annotated frame AND structured detection data
  - Keep a frame counter
  - Thread-safe via threading.Lock
"""
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import numpy as np

from api.config import settings
from api.models import BBox, Detection


@dataclass
class _Opts:
    """
    Lightweight opts object that ALPRCore expects.
    Mirrors the argparse namespace from the CLI.
    """
    vehicle_weight: str = ""
    plate_weight: str = ""
    dsort_weight: str = "models/deepsort/ckpt.t7"
    vconf: float = 0.6
    pconf: float = 0.25
    ocr_thres: float = 0.9
    read_plate: bool = True
    deepsort: bool = False
    device: str = "0"
    lang: str = "en"


class ALPRService:
    """
    Singleton service that owns the ALPR pipeline.
    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame_count = 0
        self._core = None  # Lazy-loaded

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        """Load models. Called once during app lifespan startup."""
        from utils.alpr_core import ALPRCore  # heavy import

        opts = _Opts(
            vehicle_weight=settings.vehicle_weight,
            plate_weight=settings.plate_weight,
            dsort_weight=settings.dsort_weight,
            vconf=settings.vconf,
            pconf=settings.pconf,
            ocr_thres=settings.ocr_thres,
            read_plate=settings.read_plate,
            deepsort=settings.deepsort,
            device=settings.device,
            lang=settings.lang,
        )
        self._core = ALPRCore(opts)

    def shutdown(self) -> None:
        """Release resources."""
        with self._lock:
            self._core = None
            self._frame_count = 0

    @property
    def is_ready(self) -> bool:
        return self._core is not None

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def process_and_extract(
        self,
        frame: np.ndarray,
        reset_tracker: bool = False,
    ) -> tuple:
        """
        Run the ALPR pipeline on a single frame.

        Args:
            frame: BGR numpy array (from cv2)
            reset_tracker: If True, resets tracking state first (for single images)

        Returns:
            (annotated_frame, detections_list, frame_count)
        """
        with self._lock:
            if self._core is None:
                raise RuntimeError("ALPRService not initialized. Call startup() first.")

            if reset_tracker:
                self._core.reset()

            annotated = self._core.process_frame(frame)
            self._frame_count += 1

            detections = self._extract_detections()
            return annotated, detections, self._frame_count

    def reset(self) -> None:
        """Reset tracker state and frame counter."""
        with self._lock:
            if self._core is not None:
                self._core.reset()
            self._frame_count = 0

    # ------------------------------------------------------------------
    # Runtime config updates
    # ------------------------------------------------------------------

    def update_config(self, **kwargs) -> None:
        """
        Update detection thresholds and flags at runtime.
        Supported keys: vconf, pconf, ocr_thres, read_plate, lang, device
        """
        with self._lock:
            if self._core is None:
                return
            opts = self._core.opts
            for key, value in kwargs.items():
                if value is not None and hasattr(opts, key):
                    setattr(opts, key, value)
            # Sync relevant core attributes
            if "ocr_thres" in kwargs and kwargs["ocr_thres"] is not None:
                self._core.ocr_thres = float(kwargs["ocr_thres"])
            if "read_plate" in kwargs and kwargs["read_plate"] is not None:
                self._core.read_plate = bool(kwargs["read_plate"])

    def get_config(self) -> dict:
        """Return current runtime configuration."""
        with self._lock:
            if self._core is None:
                return {}
            opts = self._core.opts
            return {
                "vehicle_weight": opts.vehicle_weight,
                "plate_weight": opts.plate_weight,
                "device": str(opts.device),
                "vconf": opts.vconf,
                "pconf": opts.pconf,
                "ocr_thres": self._core.ocr_thres,
                "read_plate": self._core.read_plate,
                "deepsort": self._core.deepsort,
                "lang": getattr(opts, "lang", "en"),
            }

    @property
    def frame_count(self) -> int:
        return self._frame_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_detections(self) -> List[Detection]:
        """
        Read self._core.vehicles dict and build a list of Detection schemas.
        Called while holding self._lock.
        """
        detections: List[Detection] = []
        if self._core is None:
            return detections

        for tid, vehicle in self._core.vehicles.items():
            # Skip vehicles without a bounding box (stale entries)
            if vehicle.bbox_xyxy is None:
                continue

            bbox = vehicle.bbox_xyxy
            det = Detection(
                track_id=int(tid),
                bbox=BBox(
                    x1=float(bbox[0]),
                    y1=float(bbox[1]),
                    x2=float(bbox[2]),
                    y2=float(bbox[3]),
                ),
                vehicle_type=vehicle.vehicle_type or "",
                license_plate=vehicle.plate_number if vehicle.plate_number != "nan" else "",
                confidence=float(vehicle.ocr_conf),
            )

            # Add plate bounding box if available
            if vehicle.license_plate_bbox is not None:
                pb = vehicle.license_plate_bbox
                det.plate_bbox = BBox(
                    x1=float(pb[0]),
                    y1=float(pb[1]),
                    x2=float(pb[2]),
                    y2=float(pb[3]),
                )

            detections.append(det)

        return detections
