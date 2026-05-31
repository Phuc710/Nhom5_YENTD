"""
Reusable OCR-only module for license plate recognition.

This file is intentionally self-contained so it can be moved to another
project with minimal changes.
"""
from __future__ import annotations

import inspect
import re
from typing import List, Sequence, Tuple

import cv2
import numpy as np
from paddleocr import PaddleOCR


PlateOCRResult = Tuple[str, float]


def enhance_plate_image(plate_bgr: np.ndarray) -> np.ndarray:
    """
    Light preprocessing tuned for cropped license plates.
    Keeps output as 3-channel BGR because PaddleOCR expects color input.
    """
    gray = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    blur = cv2.GaussianBlur(contrast, (0, 0), sigmaX=1.0)
    sharp = cv2.addWeighted(contrast, 1.4, blur, -0.4, 0)
    return cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)


def normalize_plate_text(text: str) -> str:
    """
    Normalize OCR output into a compact license-plate-friendly string.
    """
    cleaned = re.sub(r"[^A-Za-z0-9\\-.]", "", text or "")
    cleaned = cleaned.upper()

    # Keep the original project heuristic because it performed well on this set.
    if cleaned and len(cleaned) > 2 and cleaned[0].isalpha() and cleaned[2] == "C":
        cleaned = cleaned[:2] + "0" + cleaned[3:]
    return cleaned


class LicensePlateOCR:
    """
    OCR-only recognizer for cropped license plate images.

    Example:
        recognizer = LicensePlateOCR()
        text, conf = recognizer(plate_bgr)
    """

    def __init__(
        self,
        use_preprocess: bool = True,
        **paddle_kwargs,
    ) -> None:
        default_kwargs = {
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        default_kwargs.update(paddle_kwargs)

        try:
            if "use_gpu" not in default_kwargs and "use_gpu" in inspect.signature(PaddleOCR.__init__).parameters:
                default_kwargs["use_gpu"] = False
        except (TypeError, ValueError):
            pass

        self.use_preprocess = use_preprocess
        self.engine = PaddleOCR(**default_kwargs)

    def _prepare_image(self, plate_bgr: np.ndarray) -> np.ndarray:
        if plate_bgr is None or getattr(plate_bgr, "size", 0) == 0:
            raise ValueError("plate_bgr must be a non-empty BGR image")
        if self.use_preprocess:
            return enhance_plate_image(plate_bgr)
        return plate_bgr

    def _predict_with_predict(self, plate_bgr: np.ndarray) -> PlateOCRResult:
        results = self.engine.predict(input=plate_bgr)
        if not results:
            return "", 0.0

        rec_texts: Sequence[str] = results[0].get("rec_texts", [])
        rec_scores: Sequence[float] = results[0].get("rec_scores", [])
        text = normalize_plate_text(" ".join(rec_texts))
        conf = float(sum(rec_scores) / len(rec_scores)) if rec_scores else 0.0
        return text, conf

    def _predict_with_ocr(self, plate_bgr: np.ndarray) -> PlateOCRResult:
        results = self.engine.ocr(plate_bgr, cls=False)
        if not results or not results[0]:
            return "", 0.0

        texts: List[str] = [item[1][0] for item in results[0] if len(item) > 1]
        scores: List[float] = [float(item[1][1]) for item in results[0] if len(item) > 1]
        text = normalize_plate_text(" ".join(texts))
        conf = float(sum(scores) / len(scores)) if scores else 0.0
        return text, conf

    def predict(self, plate_bgr: np.ndarray) -> PlateOCRResult:
        prepared = self._prepare_image(plate_bgr)

        if hasattr(self.engine, "predict"):
            try:
                return self._predict_with_predict(prepared)
            except Exception:
                pass

        return self._predict_with_ocr(prepared)

    def __call__(self, plate_bgr: np.ndarray) -> PlateOCRResult:
        return self.predict(plate_bgr)
