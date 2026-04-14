"""
ALPRService — Thread-safe singleton wrapping ALPRCore.
"""
import os
import threading
from typing import List, Optional, Tuple

import numpy as np

from utils.alpr_core import ALPRCore, PlateResult


class ALPRService:
    """
    Singleton. Thread-safe.
    Call startup() once, then call process_frame() from any thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._core: Optional[ALPRCore] = None
        self._frame_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(
        self,
        plate_weight: str,
        device: str = "auto",
        pconf: float = 0.25,
        ocr_thres: float = 0.5,
    ) -> None:
        """Load models. Call once at app startup."""
        with self._lock:
            self._core = ALPRCore(
                plate_weight=plate_weight,
                device=device,
                pconf=pconf,
                ocr_thres=ocr_thres,
            )

    def shutdown(self) -> None:
        with self._lock:
            self._core = None
            self._frame_count = 0

    @property
    def is_ready(self) -> bool:
        return self._core is not None

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[PlateResult], int]:
        """
        Run plate detection + OCR on a single frame.

        Returns:
            annotated_frame, list of PlateResult, frame_count
        """
        with self._lock:
            if self._core is None:
                raise RuntimeError("ALPRService is not started. Call startup() first.")
            annotated, results = self._core.process_frame(frame)
            self._frame_count += 1
            return annotated, results, self._frame_count

    # ------------------------------------------------------------------
    # Runtime config
    # ------------------------------------------------------------------

    def update_config(self, pconf: float = None, ocr_thres: float = None) -> None:
        with self._lock:
            if self._core is None:
                return
            if pconf is not None:
                self._core.pconf = float(pconf)
            if ocr_thres is not None:
                self._core.ocr_thres = float(ocr_thres)

    def get_config(self) -> dict:
        with self._lock:
            if self._core is None:
                return {}
            return {
                "device": self._core.device,
                "pconf": self._core.pconf,
                "ocr_thres": self._core.ocr_thres,
            }

    @property
    def frame_count(self) -> int:
        return self._frame_count


# Module-level singleton
_instance: Optional[ALPRService] = None


def get_alpr_service() -> ALPRService:
    global _instance
    if _instance is None:
        _instance = ALPRService()
    return _instance
