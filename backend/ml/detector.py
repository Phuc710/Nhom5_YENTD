"""Dịch vụ nhận diện biển số tối ưu cho GPU RTX và chạy lâu dài."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch

from backend.config.settings import settings
from backend.function.helper import format_plate_characters
from backend.function.utils_rotate import changeContrast, deskew
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_legacy_yolov5_imports() -> None:
    """Cho phép torch load checkpoint YOLOv5 cũ đang tham chiếu `models.yolo`."""
    yolov5_root = Path(__file__).resolve().parents[1] / "yolov5"
    yolov5_root_str = str(yolov5_root)
    if yolov5_root.exists() and yolov5_root_str not in sys.path:
        sys.path.insert(0, yolov5_root_str)
        logger.info("Đã thêm đường dẫn YOLOv5 cục bộ để nạp checkpoint cũ: %s", yolov5_root_str)


_ensure_legacy_yolov5_imports()


def _mean_ms(samples: Deque[float]) -> float:
    return (sum(samples) / len(samples) * 1000.0) if samples else 0.0


_legacy_yolov5_ops: Optional[Dict[str, Any]] = None


def _get_legacy_yolov5_ops() -> Dict[str, Any]:
    global _legacy_yolov5_ops
    if _legacy_yolov5_ops is None:
        from models.experimental import attempt_load  # type: ignore
        from utils.augmentations import letterbox  # type: ignore
        from utils.general import non_max_suppression, scale_boxes  # type: ignore

        _legacy_yolov5_ops = {
            "attempt_load": attempt_load,
            "letterbox": letterbox,
            "non_max_suppression": non_max_suppression,
            "scale_boxes": scale_boxes,
        }
    return _legacy_yolov5_ops


@contextmanager
def _suppress_noisy_model_output():
    """Ẩn các dòng print trực tiếp từ thư viện model khi nạp/fuse."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


class LicensePlateDetector:
    def __init__(
        self,
        detector_model_path: Optional[str] = None,
        ocr_model_path: Optional[str] = None,
    ):
        """Khởi tạo mô hình phát hiện và OCR một lần duy nhất."""
        self.device = self._resolve_device()
        self.use_half = bool(settings.ml_use_half and self.device.startswith("cuda"))
        self.detector_imgsz = int(settings.ml_detector_imgsz)
        self.ocr_imgsz = int(settings.ml_ocr_imgsz)
        self.max_det = int(settings.ml_max_det)

        if self.device.startswith("cuda"):
            torch.backends.cudnn.benchmark = True
            try:
                torch.set_float32_matmul_precision("high")
            except Exception:
                pass

        logger.info(
            "Khởi tạo bộ nhận diện trên thiết bị=%s half=%s detector_imgsz=%s ocr_imgsz=%s",
            self.device,
            self.use_half,
            self.detector_imgsz,
            self.ocr_imgsz,
        )

        detector_path = self._resolve_model_path(detector_model_path or settings.detector_model_path)
        ocr_path = self._resolve_model_path(ocr_model_path or settings.ocr_model_path)
        self.detector_model_path = detector_path
        self.ocr_model_path = ocr_path

        logger.info("Nạp mô hình phát hiện biển số: %s", detector_path)
        self.detector = self._load_legacy_model(detector_path)

        logger.info("Nạp mô hình OCR biển số: %s", ocr_path)
        self.ocr_model = self._load_legacy_model(ocr_path)

        self.conf_threshold = settings.confidence_threshold
        self.iou_threshold = settings.iou_threshold

        window = max(int(settings.ml_metrics_window), 16)
        self.metrics = {
            "detection_time": deque(maxlen=window),
            "ocr_time": deque(maxlen=window),
            "detection_count": 0,
            "ocr_count": 0,
            "errors": 0,
        }

        self.char_map = {
            0: "0", 1: "1", 2: "2", 3: "3", 4: "4",
            5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
            10: "A", 11: "B", 12: "C", 13: "D", 14: "E",
            15: "F", 16: "G", 17: "H", 18: "K", 19: "L",
            20: "M", 21: "N", 22: "P", 23: "S", 24: "T",
            25: "U", 26: "V", 27: "X", 28: "Y", 29: "Z",
            30: "-",
            31: ".",
        }

        if settings.ml_warmup_runs > 0:
            self._warmup()

        logger.info("Khởi tạo bộ nhận diện thành công")

    @staticmethod
    def _resolve_model_path(model_path: str) -> str:
        resolved = os.path.abspath(str(model_path))
        return resolved

    def _resolve_device(self) -> str:
        requested = str(settings.ml_device or "auto").strip().lower()
        if requested in {"auto", ""}:
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        return requested

    def _load_legacy_model(self, model_path: str):
        ops = _get_legacy_yolov5_ops()
        attempt_load = ops["attempt_load"]
        original_torch_load = torch.load

        def _compat_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_torch_load(*args, **kwargs)

        try:
            torch.load = _compat_load
            with _suppress_noisy_model_output():
                model = attempt_load(model_path, device=self.device, fuse=True)
        finally:
            torch.load = original_torch_load

        if self.use_half and hasattr(model, "half"):
            model.half()
        else:
            model.float()
        model.eval()
        return model

    def _run_legacy_inference(
        self,
        model,
        image: np.ndarray,
        *,
        imgsz: int,
        conf: float,
        iou: float,
        max_det: int,
    ) -> List[List[float]]:
        ops = _get_legacy_yolov5_ops()
        letterbox = ops["letterbox"]
        non_max_suppression = ops["non_max_suppression"]
        scale_boxes = ops["scale_boxes"]

        stride = int(getattr(model, "stride", torch.tensor([32])).max())
        padded = letterbox(image, new_shape=imgsz, stride=stride, auto=False)[0]
        tensor = padded.transpose((2, 0, 1))[::-1]
        tensor = np.ascontiguousarray(tensor)
        tensor = torch.from_numpy(tensor).to(self.device)
        tensor = tensor.half() if self.use_half else tensor.float()
        tensor /= 255.0
        if tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)

        prediction = model(tensor)
        if isinstance(prediction, (tuple, list)):
            prediction = prediction[0]
        results = non_max_suppression(prediction, conf, iou, max_det=max_det)

        detections: List[List[float]] = []
        if results:
            det = results[0]
            if det is not None and len(det):
                det = det.clone()
                det[:, :4] = scale_boxes(tensor.shape[2:], det[:, :4], image.shape).round()
                detections = det.detach().cpu().numpy().tolist()
        return detections

    def _warmup(self) -> None:
        """Làm nóng CUDA/context để request đầu tiên không bị khựng."""
        if os.getenv("SKIP_WARMUP"):
            logger.info("Skipping warmup as requested")
            return
        try:
            dummy_frame = np.zeros((self.detector_imgsz, self.detector_imgsz, 3), dtype=np.uint8)
            dummy_plate = np.zeros((self.ocr_imgsz, self.ocr_imgsz, 3), dtype=np.uint8)
            for _ in range(max(int(settings.ml_warmup_runs), 1)):
                self._run_legacy_inference(
                    self.detector,
                    dummy_frame,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    imgsz=self.detector_imgsz,
                    max_det=self.max_det,
                )
                self._run_legacy_inference(
                    self.ocr_model,
                    dummy_plate,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    imgsz=self.ocr_imgsz,
                    max_det=max(self.max_det * 4, 8),
                )
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            logger.info("Đã warmup mô hình %s lần", settings.ml_warmup_runs)
        except Exception as exc:
            logger.warning("Warmup mô hình thất bại, tiếp tục chạy thường: %s", exc)

    def detect_plates(self, image: np.ndarray) -> List[Dict]:
        """Phát hiện biển số trong ảnh và trả về danh sách bbox."""
        start_time = time.perf_counter()

        try:
            with torch.inference_mode():
                results = self._run_legacy_inference(
                    self.detector,
                    image,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    imgsz=self.detector_imgsz,
                    max_det=self.max_det,
                )
                if self.device.startswith("cuda"):
                    torch.cuda.synchronize()

            plates = []
            for index, box in enumerate(results):
                x1, y1, x2, y2, conf, _cls = box[:6]
                plates.append({
                    "bbox": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)},
                    "confidence": float(conf),
                    "plate_index": index,
                })

            elapsed = time.perf_counter() - start_time
            self.metrics["detection_time"].append(elapsed)
            self.metrics["detection_count"] += len(plates)
            logger.debug("Detect %s biển số trong %.1fms", len(plates), elapsed * 1000)
            return plates

        except Exception as exc:
            self.metrics["errors"] += 1
            logger.error("Nhận diện biển số thất bại: %s", exc)
            raise

    def crop_plate(self, image: np.ndarray, bbox: Dict) -> np.ndarray:
        """Cắt riêng vùng biển số từ ảnh gốc."""
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        return image[y1:y2, x1:x2]

    def ocr_plate(self, plate_image: np.ndarray) -> Tuple[str, float]:
        """OCR vùng biển số đã cắt và trả về văn bản cùng độ tin cậy."""
        start_time = time.perf_counter()

        try:
            best_text = ""
            best_conf = 0.0
            best_score = -1.0

            for variant_name, candidate_image in self._iter_ocr_candidates(plate_image):
                with torch.inference_mode():
                    results = self._run_legacy_inference(
                        self.ocr_model,
                        candidate_image,
                        conf=self.conf_threshold,
                        iou=self.iou_threshold,
                        imgsz=self.ocr_imgsz,
                        max_det=max(self.max_det * 4, 8),
                    )
                    if self.device.startswith("cuda"):
                        torch.cuda.synchronize()

                if not results:
                    continue

                detections = self._extract_ocr_detections(results)
                if not detections:
                    continue

                plate_text = format_plate_characters(detections)
                avg_conf = float(np.mean([item["conf"] for item in detections])) if detections else 0.0
                if plate_text in {"", "unknown"}:
                    plate_text = self._decode_plate(detections)

                score = avg_conf + min(len(plate_text.replace("-", "")), 10) * 0.02
                if "-" in plate_text:
                    score += 0.02

                if score > best_score and plate_text:
                    best_score = score
                    best_text = plate_text
                    best_conf = avg_conf
                    logger.debug(
                        "OCR variant=%s plate='%s' conf=%.3f score=%.3f",
                        variant_name,
                        plate_text,
                        avg_conf,
                        score,
                    )

            elapsed = time.perf_counter() - start_time
            self.metrics["ocr_time"].append(elapsed)
            self.metrics["ocr_count"] += 1

            if best_text:
                logger.debug("OCR '%s' trong %.1fms", best_text, elapsed * 1000)
                return best_text, best_conf

            logger.debug("Không nhận ra ký tự nào trên biển số")
            return "", 0.0

        except Exception as exc:
            self.metrics["errors"] += 1
            logger.error("OCR biển số thất bại: %s", exc)
            raise

    def _decode_plate(self, detections: List[Dict]) -> str:
        """Ghép chuỗi biển số từ kết quả OCR ký tự."""
        chars = []
        for detection in detections:
            char = self.char_map.get(detection["class"], "?")
            if char == "?":
                logger.debug("Gặp class OCR chưa ánh xạ: %s", detection["class"])
            chars.append(char)
        return "".join(chars)

    def _iter_ocr_candidates(self, plate_image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        candidates: List[Tuple[str, np.ndarray]] = []
        cleaned = self._sanitize_plate_image(plate_image)
        if cleaned is None:
            return candidates

        candidates.append(("raw", cleaned))

        try:
            contrast = changeContrast(cleaned)
            candidates.append(("contrast", contrast))
        except Exception:
            contrast = cleaned

        for variant_name, variant_image in (("deskew", cleaned), ("deskew_contrast", contrast)):
            try:
                rotated = deskew(variant_image, 1, 1)
                sanitized = self._sanitize_plate_image(rotated)
                candidates.append((variant_name, sanitized if sanitized is not None else variant_image))
            except Exception:
                continue

        unique_candidates: List[Tuple[str, np.ndarray]] = []
        seen_signatures: set[bytes] = set()
        for name, image in candidates:
            if image is None or image.size == 0:
                continue
            signature = image.tobytes()[:128]
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_candidates.append((name, image))
        return unique_candidates

    def _extract_ocr_detections(self, result: List[List[float]]) -> List[Dict[str, Any]]:
        detections: List[Dict[str, Any]] = []
        for box in result:
            x1, y1, x2, y2, conf, cls = box[:6]
            detections.append({
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2),
                "x": int(x1),
                "class": int(cls),
                "conf": float(conf),
                "label": self.char_map.get(int(cls), ""),
            })
        detections.sort(key=lambda item: item["x1"])
        return detections

    @staticmethod
    def _sanitize_plate_image(plate_image: np.ndarray) -> Optional[np.ndarray]:
        if plate_image is None or plate_image.size == 0:
            return None
        image = plate_image
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.shape[0] < 24 or image.shape[1] < 48:
            image = cv2.resize(
                image,
                (max(96, image.shape[1] * 2), max(48, image.shape[0] * 2)),
                interpolation=cv2.INTER_CUBIC,
            )
        return image

    def process_frame(self, image: np.ndarray) -> List[Dict]:
        """Chạy trọn pipeline detect + OCR trên ảnh đã giải mã sẵn."""
        try:
            if image is None or image.size == 0:
                raise ValueError("Ảnh đầu vào rỗng")

            plates = self.detect_plates(image)
            if not plates:
                return []

            results = []
            for plate in plates:
                try:
                    plate_img = self.crop_plate(image, plate["bbox"])
                    plate_text, ocr_conf = self.ocr_plate(plate_img)
                    results.append({
                        "bbox": plate["bbox"],
                        "detection_confidence": plate["confidence"],
                        "plate_text": plate_text,
                        "ocr_confidence": ocr_conf,
                        "overall_confidence": (plate["confidence"] + ocr_conf) / 2,
                        "confidence": ocr_conf,
                    })
                except Exception as exc:
                    logger.error("Xử lý biển số #%s thất bại: %s", plate["plate_index"], exc)

            return results

        except Exception as exc:
            logger.error("Xử lý ảnh nhận diện thất bại: %s", exc)
            return []

    def process_image(self, image_path: str) -> List[Dict]:
        """Giữ tương thích cũ cho luồng đọc ảnh từ đường dẫn."""
        try:
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Không đọc được ảnh: {image_path}")
            return self.process_frame(image)
        except Exception as exc:
            logger.error("Xử lý ảnh từ đường dẫn thất bại: %s", exc)
            return []

    def get_metrics(self) -> Dict:
        """Trả về thống kê hiệu năng hiện tại của bộ nhận diện."""
        return {
            "avg_detection_time_ms": _mean_ms(self.metrics["detection_time"]),
            "avg_ocr_time_ms": _mean_ms(self.metrics["ocr_time"]),
            "total_detections": self.metrics["detection_count"],
            "total_ocr": self.metrics["ocr_count"],
            "total_errors": self.metrics["errors"],
            "device": self.device,
            "half_precision": self.use_half,
        }


_detector_instance: Optional[LicensePlateDetector] = None


def get_detector() -> LicensePlateDetector:
    """Lấy singleton detector để tái sử dụng model đã nạp."""
    global _detector_instance
    if _detector_instance is None:
        logger.info("Tạo mới singleton detector")
        _detector_instance = LicensePlateDetector()
    return _detector_instance
