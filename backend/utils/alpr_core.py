"""
ALPRCore — Detect license plate bbox → OCR text.
No vehicle detection. No tracking. Fast & clean.
"""
from typing import List, Optional, Tuple
import time

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from utils.license_plate_ocr import LicensePlateOCR


def _resolve_device(requested: Optional[str]) -> str:
    if not requested or requested == "auto":
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    if requested.isdigit():
        return f"cuda:{requested}" if torch.cuda.is_available() else "cpu"
    if requested == "cuda":
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        return "cpu"
    return requested


def _crop_plate(frame: np.ndarray, xyxy: np.ndarray, expand: float = 0.05) -> np.ndarray:
    """Crop plate region with small padding, clipped to frame."""
    x1, y1, x2, y2 = xyxy.astype(int)
    h, w = frame.shape[:2]
    pw = int((x2 - x1) * expand)
    ph = int((y2 - y1) * expand)
    x1 = max(0, x1 - pw)
    y1 = max(0, y1 - ph)
    x2 = min(w, x2 + pw)
    y2 = min(h, y2 + ph)
    return frame[y1:y2, x1:x2]


class PlateResult:
    """Result for a single detected plate."""
    __slots__ = ("bbox_xyxy", "plate_image", "text", "conf")

    def __init__(self, bbox_xyxy: np.ndarray, plate_image: np.ndarray, text: str = "", conf: float = 0.0):
        self.bbox_xyxy = bbox_xyxy
        self.plate_image = plate_image
        self.text = text
        self.conf = conf


class ALPRCore:
    """
    Plate detection + OCR pipeline.

    Flow:
        frame → plate YOLO detector → crop plates → RapidOCR → list[PlateResult]
    """

    def __init__(self, plate_weight: str, device: str = "auto", pconf: float = 0.25, ocr_thres: float = 0.5):
        self.device = _resolve_device(device)
        self._is_cuda = self.device.startswith("cuda")
        self.pconf = pconf
        self.ocr_thres = ocr_thres

        # Plate detector
        self.plate_detector = YOLO(plate_weight, task="detect")
        try:
            self.plate_detector.to(self.device)
        except Exception:
            pass

        # OCR engine
        self.ocr = LicensePlateOCR(use_gpu=self._is_cuda)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[PlateResult]]:
        """
        Detect plates in frame, run OCR on each.

        Returns:
            annotated_frame: frame with drawn bboxes + text
            results: list of PlateResult
        """
        if frame is None or frame.size == 0:
            return frame, []

        out = frame.copy()
        t0 = time.perf_counter()

        results: List[PlateResult] = []

        # 1. Plate detection on full frame
        detections = self.plate_detector(
            frame,
            verbose=False,
            imgsz=640,
            device=self.device,
            conf=self.pconf,
        )[0]

        boxes = detections.boxes
        if boxes is None or len(boxes) == 0:
            self._draw_fps(out, t0)
            return out, results

        for xyxy in boxes.xyxy.cpu().numpy():
            # 2. Crop plate
            plate_img = _crop_plate(frame, xyxy)
            if plate_img.size == 0 or plate_img.shape[0] < 8 or plate_img.shape[1] < 8:
                continue

            # 3. OCR
            text, conf = self.ocr(plate_img)

            pr = PlateResult(bbox_xyxy=xyxy.astype(int), plate_image=plate_img, text=text, conf=conf)
            results.append(pr)

            # 4. Draw
            x1, y1, x2, y2 = xyxy.astype(int)
            color = (0, 220, 0) if conf >= self.ocr_thres else (0, 165, 255)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            label = text if text else "plate"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(out, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)

        self._draw_fps(out, t0)
        return out, results

    def process_image(self, img: np.ndarray) -> Tuple[np.ndarray, List[PlateResult]]:
        """Same as process_frame but for single still images."""
        return self.process_frame(img)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_fps(frame: np.ndarray, t0: float) -> None:
        dt = time.perf_counter() - t0
        fps = f"FPS: {1.0 / dt:.0f}" if dt > 0 else "FPS: --"
        cv2.putText(frame, fps, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, fps, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
