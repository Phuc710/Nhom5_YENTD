"""
detector.py — License plate detection + OCR tối ưu cho biển nhỏ VN.

Flow:
  preprocess (Bilateral + CLAHE)
  → tile detect (SAHI-style)
  → filter: Area + Aspect Ratio VN
  → crop + adaptive pad
  → SR Lanczos + Unsharp
  → CLAHE crop
  → Deskew (Hough + minAreaRect fallback)
  → multi-attempt OCR (3 chiến lược)
  → temporal voting (8 frames)
"""
from __future__ import annotations

import os
import re
import threading
import time
import warnings
from typing import Dict, List, Optional

import cv2
import numpy as np
import torch

from backend.config.settings import settings
from backend.utils.logger import get_logger
from backend.utils.license_plate_ocr import LicensePlateOCR

logger = get_logger(__name__)

try:
    from backend.function import utils_rotate
except ImportError:
    utils_rotate = None  # type: ignore

helper = None  # LP_ocr.pt không còn dùng nữa


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes: list, iou_thr: float = 0.45) -> list:
    boxes = sorted(boxes, key=lambda x: x[4], reverse=True)
    keep: list = []
    while boxes:
        best = boxes.pop(0)
        keep.append(best)
        boxes = [b for b in boxes if _iou(best[:4], b[:4]) < iou_thr]
    return keep


# ── Image helpers ──────────────────────────────────────────────────────────────

def _clahe(frame: np.ndarray) -> np.ndarray:
    """CLAHE inline fallback."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _enhance(frame: np.ndarray) -> np.ndarray:
    """CLAHE qua utils_rotate nếu có, không thì inline."""
    return utils_rotate.changeContrast(frame) if utils_rotate else _clahe(frame)


def _sr_upscale(crop: np.ndarray, scale: int = 4) -> np.ndarray:
    """LANCZOS4 upscale + unsharp mask nhẹ (tốt hơn kernel cứng [-1,9,-1])."""
    h, w = crop.shape[:2]
    up   = cv2.resize(crop, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(up, (0, 0), sigmaX=1.5)
    return cv2.addWeighted(up, 1.6, blur, -0.6, 0)


def _safe_deskew(crop: np.ndarray) -> np.ndarray:
    """
    Deskew an toàn:
    - change_cons=0 vì đã enhance bên ngoài rồi
    - skip nếu width < 80px (Hough không đáng tin trên ảnh quá nhỏ)
    """
    if utils_rotate is None or crop.shape[1] < 80:
        return crop
    try:
        return utils_rotate.deskew(crop, change_cons=0, center_thres=0)
    except Exception:
        return crop


# ── Tile detection (SAHI-style) ────────────────────────────────────────────────

def _detect_tiles(
    model,
    frame: np.ndarray,
    imgsz: int = 640,
    tile_size: int = 640,
    overlap: float = 0.25,
) -> np.ndarray:
    """Chia frame thành tile chồng nhau, detect + NMS. Bắt biển nhỏ tốt hơn."""
    h, w = frame.shape[:2]
    if w <= tile_size and h <= tile_size:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return model(frame, size=imgsz).xyxy[0].cpu().numpy()

    step     = int(tile_size * (1 - overlap))
    all_dets: list = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for y0 in range(0, h, step):
            for x0 in range(0, w, step):
                tile = frame[y0:min(y0+tile_size, h), x0:min(x0+tile_size, w)]
                if tile.size == 0:
                    continue
                for d in model(tile, size=tile_size).xyxy[0].cpu().numpy():
                    tx1, ty1, tx2, ty2, c, cls = d
                    all_dets.append([tx1+x0, ty1+y0, tx2+x0, ty2+y0,
                                     float(c), float(cls)])
    kept = _nms(all_dets)
    return np.array(kept, dtype=np.float32) if kept else np.zeros((0, 6))


# ── Main class ─────────────────────────────────────────────────────────────────

class LicensePlateDetector:
    # Detection
    CONF      = 0.35
    OCR_CONF  = 0.45
    IOU       = 0.35
    MIN_AREA  = 400   # ← lowered from 800 to catch smaller plates
    MAX_WIDTH = 1280

    # Aspect ratio VN (width / height)
    CAR_RATIO_MIN  = 1.5   # ← lowered from 3.0 to support square car plates (330x165mm)
    CAR_RATIO_MAX  = 6.5
    MOTO_RATIO_MIN = 0.8
    MOTO_RATIO_MAX = 2.2

    # Super-resolution
    SMALL_W        = 80
    SR_SCALE_TINY  = 6
    SR_SCALE_SMALL = 4

    # Crop padding
    PAD_SMALL  = 20
    PAD_NORMAL = 6

    # Tiling
    TILE_SIZE    = 640
    TILE_OVERLAP = 0.25

    def __init__(
        self,
        detector_model_path: Optional[str] = None,
        ocr_model_path: Optional[str] = None,
    ) -> None:
        self.device   = self._resolve_device()
        self.conf     = float(getattr(settings, "confidence_threshold", self.CONF) or self.CONF)
        self.iou      = float(getattr(settings, "iou_threshold", self.IOU) or self.IOU)
        self.use_half = bool(settings.ml_use_half and self.device not in {"cpu", ""})

        self.detector_model_path = detector_model_path or settings.detector_model_path

        self._det: Optional[object] = None
        self._lock = threading.Lock()
        self.models_loaded = False

        # OCR mới: RapidOCR ONNX (không dùng LP_ocr.pt)
        self._rapidocr = LicensePlateOCR(use_gpu=self.device not in {"cpu", ""})
        logger.info("✅ OCR: RapidOCR ONNX engine")

        self.load_models()
        if settings.ml_warmup_runs > 0:
            self._warmup()

    # ── Device ────────────────────────────────────────────────────────────────

    def _resolve_device(self) -> str:
        req = str(settings.ml_device or "auto").strip().lower()
        if req not in {"auto", ""}:
            return "0" if req == "cuda" else req
        if torch.cuda.is_available():
            try:
                torch.zeros(1).to("cuda")
                return "0"
            except Exception:
                pass
        return "cpu"

    # ── Load ──────────────────────────────────────────────────────────────────

    def load_models(self) -> bool:
        if self.models_loaded:
            return True
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                if os.path.exists(self.detector_model_path):
                    self._det = torch.hub.load(
                        "ultralytics/yolov5", "custom",
                        path=self.detector_model_path,
                        force_reload=False, device=self.device, trust_repo=True,
                    )
                    logger.info("✅ Detector: %s", self.detector_model_path)
                else:
                    self._det = torch.hub.load(
                        "ultralytics/yolov5", "yolov5s",
                        device=self.device, trust_repo=True,
                    )
                    logger.warning("⚠️  Detector model not found, fallback yolov5s")

                self._det.conf = self.conf
                self._det.iou  = self.iou

                if self.use_half and self._det:
                    self._det.half()
                    logger.info("⚡ Half-precision (FP16) enabled")

            self.models_loaded = True
            return True
        except Exception as exc:
            logger.error("❌ load_models failed: %s", exc)
            return False

    # ── Warmup ────────────────────────────────────────────────────────────────

    def _warmup(self) -> None:
        if not self.models_loaded:
            return
        dummy_det = np.zeros((settings.ml_detector_imgsz,) * 2 + (3,), dtype=np.uint8)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for _ in range(max(int(settings.ml_warmup_runs), 1)):
                    if self._det:
                        self._det(dummy_det, size=settings.ml_detector_imgsz)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            logger.info("🔥 Warmup OK (%d runs)", settings.ml_warmup_runs)
        except Exception as exc:
            logger.warning("⚠️  Warmup failed: %s", exc)

    # ── Preprocess ────────────────────────────────────────────────────────────

    def _preprocess(self, frame: np.ndarray, config: Optional[Dict] = None) -> np.ndarray:
        cfg = config or {}
        if cfg.get("rotate_180", settings.ml_rotate_180):
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        if cfg.get("flip_horizontal", settings.ml_flip_horizontal):
            frame = cv2.flip(frame, 1)

        h, w = frame.shape[:2]
        if w > self.MAX_WIDTH:
            frame = cv2.resize(frame, (self.MAX_WIDTH, int(h * self.MAX_WIDTH / w)),
                               interpolation=cv2.INTER_AREA)

        return _enhance(frame)

    # ── Aspect ratio filter ────────────────────────────────────────────────────

    def _aspect_ratio_ok(self, x1, y1, x2, y2) -> bool:
        """Chỉ giữ bbox có tỉ lệ hợp lệ của biển VN (ô tô hoặc xe máy)."""
        w = float(x2 - x1)
        h = float(y2 - y1)
        if h <= 0:
            return False
        ratio = w / h
        return (self.CAR_RATIO_MIN  <= ratio <= self.CAR_RATIO_MAX or
                self.MOTO_RATIO_MIN <= ratio <= self.MOTO_RATIO_MAX)

    # ── Crop + padding ────────────────────────────────────────────────────────

    def _crop_plate(self, frame: np.ndarray, x1, y1, x2, y2) -> np.ndarray:
        """Crop biển với padding theo hằng số PAD_SMALL / PAD_NORMAL."""
        pad = self.PAD_SMALL if (x2 - x1) < self.SMALL_W else self.PAD_NORMAL
        fh, fw = frame.shape[:2]
        return frame[max(0, y1-pad):min(fh, y2+pad),
                     max(0, x1-pad):min(fw, x2+pad)]

    def _clean_text(self, text: str) -> str:
        """Xóa các ký tự thừa (-, ., dấu cách) và in hoa."""
        if not text:
            return ""
        cleaned = re.sub(r'[^A-Za-z0-9]', '', text)
        return cleaned.upper()

    # ── Multi-attempt OCR ─────────────────────────────────────────────────────

    def _ocr_plate(self, crop: np.ndarray, plate_w: int) -> str:
        """
        OCR biển số bằng RapidOCR ONNX.
        Với biển nhỏ: SR upscale + CLAHE trước khi OCR.
        """
        if crop is None or crop.size == 0:
            return "unknown"

        # SR + CLAHE cho biển nhỏ
        if plate_w < 40:
            crop = _sr_upscale(crop, scale=self.SR_SCALE_TINY)
        elif plate_w < self.SMALL_W:
            crop = _sr_upscale(crop, scale=self.SR_SCALE_SMALL)

        crop = _enhance(crop)

        # Attempt 1: deskew rồi OCR
        try:
            deskewed = _safe_deskew(crop)
            text, conf = self._rapidocr(deskewed)
            text = self._clean_text(text)
            if text and len(text) >= 5:
                return text
        except Exception:
            pass

        # Attempt 2: không deskew
        try:
            text, conf = self._rapidocr(crop)
            text = self._clean_text(text)
            if text and len(text) >= 5:
                return text
        except Exception:
            pass

        return "unknown"

    # ── Main detect ───────────────────────────────────────────────────────────

    def detect_and_read_plate(
        self,
        frame: np.ndarray,
        config: Optional[Dict] = None,
        ocr_enabled: bool = True,
    ) -> Dict:
        if not self.models_loaded:
            return {"success": False, "plates": [], "error": "Models not loaded"}
        if frame is None or frame.size == 0:
            return {"success": False, "plates": [], "error": "Empty frame"}

        with self._lock:
            try:
                processed   = self._preprocess(frame, config)
                cfg         = config or {}
                imgsz       = cfg.get("imgsz", settings.ml_detector_imgsz)
                target_conf = float(cfg.get("confidence_threshold", self.conf))

                if self._det.conf != target_conf:
                    self._det.conf = target_conf

                # ── Detect ────────────────────────────────────────────────
                use_tile = cfg.get("use_tiling", True)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    dets = (
                        _detect_tiles(self._det, processed, imgsz=imgsz,
                                      tile_size=self.TILE_SIZE,
                                      overlap=self.TILE_OVERLAP)
                        if use_tile else
                        self._det(processed, size=imgsz).xyxy[0].cpu().numpy()
                    )

                if dets.size == 0:
                    return {"success": False, "plates": [], "error": "No plate detected"}

                # ── Filter: Area + Aspect Ratio VN ────────────────────────
                candidates = sorted(
                    [d for d in dets
                     if (d[2]-d[0])*(d[3]-d[1]) > self.MIN_AREA
                     and self._aspect_ratio_ok(d[0], d[1], d[2], d[3])],
                    key=lambda d: (d[2]-d[0])*(d[3]-d[1]),
                    reverse=True,
                )[:3]

                plates = []
                for det in candidates:
                    x1, y1, x2, y2, conf, _ = det
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    plate_w  = x2 - x1
                    is_small = plate_w < self.SMALL_W

                    # Cắt ảnh biển số (có padding)
                    crop = self._crop_plate(processed, x1, y1, x2, y2)
                    if crop.size == 0:
                        continue

                    if not ocr_enabled:
                        plates.append({
                            "bbox": (x1, y1, x2, y2),
                            "text": "",
                            "confidence": float(conf),
                            "cached": False,
                            "is_small": is_small
                        })
                        continue

                    raw = ""
                    # Cache OCR (chống giật FPS khi OCR liên tục)
                    rkey = f"{x1//20}_{y1//20}_{x2//20}_{y2//20}"
                    if rkey in getattr(self, "_cache", {}):
                        text, ts = self._cache[rkey]
                        if time.time() - ts < 1.5:  # Cache OCR trong 1.5 giây
                            raw = text

                    if not raw:
                        raw = self._ocr_plate(crop, plate_w)
                        if not hasattr(self, "_cache"):
                            self._cache = {}
                        if raw and raw != "unknown":
                            self._cache[rkey] = (raw, time.time())

                    plate_text = raw if raw and raw != "unknown" else ""

                    plates.append({
                        "bbox": (x1, y1, x2, y2),
                        "text": plate_text,
                        "confidence": float(conf),
                        "cached": bool(raw == getattr(self, "_cache", {}).get(rkey, ("", 0))[0]),
                        "cropped_image": crop,
                        "is_small": is_small
                    })

                plates.sort(key=lambda p: p["confidence"], reverse=True)
                return {"success": bool(plates), "plates": plates, "error": None}

            except Exception as exc:
                logger.error("detect_and_read_plate error: %s", exc)
                return {"success": False, "plates": [], "error": str(exc)}

    # ── Public API (compat) ───────────────────────────────────────────────────

    def process_frame(self, frame: np.ndarray, config: Optional[Dict] = None,
                      ocr_enabled: bool = True) -> List[Dict]:
        return [
            {
                "bbox": {"x1": p["bbox"][0], "y1": p["bbox"][1],
                         "x2": p["bbox"][2], "y2": p["bbox"][3]},
                "plate_text":           p["text"],
                "confidence":           p["confidence"],
                "detection_confidence": p["confidence"],
                "ocr_confidence":       p["confidence"],
                "overall_confidence":   p["confidence"],
            }
            for p in self.detect_and_read_plate(frame, config, ocr_enabled).get("plates", [])
        ]

    def process_image(self, image_path: str) -> List[Dict]:
        img = cv2.imread(image_path)
        return self.process_frame(img) if img is not None else []

    def process_image_file(self, image_path: str) -> Dict:
        if not os.path.exists(image_path):
            return {"success": False, "plates": [], "error": f"File not found: {image_path}"}
        frame = cv2.imread(image_path)
        if frame is None:
            return {"success": False, "plates": [], "error": "Cannot load image"}
        return self.detect_and_read_plate(frame)

    def get_best_plate(self, result: Dict) -> Optional[Dict]:
        plates = result.get("plates", [])
        return plates[0] if plates else None

    def get_metrics(self) -> Dict:
        return {"device": self.device, "half_precision": self.use_half,
                "models_loaded": self.models_loaded}

    def is_ready(self) -> bool:
        return self.models_loaded

    def clear_cache(self) -> None:
        pass


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[LicensePlateDetector] = None


def get_detector() -> LicensePlateDetector:
    global _instance
    if _instance is None:
        logger.info("🔧 Initialising LicensePlateDetector singleton...")
        _instance = LicensePlateDetector()
    return _instance
