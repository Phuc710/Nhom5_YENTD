"""Dịch vụ nhận diện biển số tối ưu cho GPU RTX và chạy lâu dài."""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from tenacity import retry, stop_after_attempt, wait_fixed
from ultralytics import YOLO

from backend.config.settings import settings
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


class LicensePlateDetector:
    def __init__(self):
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

        detector_path = os.path.join(os.path.dirname(__file__), settings.detector_model_path)
        ocr_path = os.path.join(os.path.dirname(__file__), settings.ocr_model_path)

        logger.info("Nạp mô hình phát hiện biển số: %s", detector_path)
        self.detector = YOLO(detector_path)
        self.detector.to(self.device)
        self._maybe_fuse(self.detector)

        logger.info("Nạp mô hình OCR biển số: %s", ocr_path)
        self.ocr_model = YOLO(ocr_path)
        self.ocr_model.to(self.device)
        self._maybe_fuse(self.ocr_model)

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

    def _resolve_device(self) -> str:
        requested = str(settings.ml_device or "auto").strip().lower()
        if requested in {"auto", ""}:
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        return requested

    @staticmethod
    def _maybe_fuse(model: YOLO) -> None:
        try:
            model.fuse()
        except Exception:
            pass

    def _warmup(self) -> None:
        """Làm nóng CUDA/context để request đầu tiên không bị khựng."""
        try:
            dummy_frame = np.zeros((self.detector_imgsz, self.detector_imgsz, 3), dtype=np.uint8)
            dummy_plate = np.zeros((self.ocr_imgsz, self.ocr_imgsz, 3), dtype=np.uint8)
            for _ in range(max(int(settings.ml_warmup_runs), 1)):
                self.detector.predict(
                    dummy_frame,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    imgsz=self.detector_imgsz,
                    max_det=self.max_det,
                    half=self.use_half,
                    verbose=False,
                    device=self.device,
                )
                self.ocr_model.predict(
                    dummy_plate,
                    conf=self.conf_threshold,
                    imgsz=self.ocr_imgsz,
                    max_det=max(self.max_det * 4, 8),
                    half=self.use_half,
                    verbose=False,
                    device=self.device,
                )
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            logger.info("Đã warmup mô hình %s lần", settings.ml_warmup_runs)
        except Exception as exc:
            logger.warning("Warmup mô hình thất bại, tiếp tục chạy thường: %s", exc)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def detect_plates(self, image: np.ndarray) -> List[Dict]:
        """Phát hiện biển số trong ảnh và trả về danh sách bbox."""
        start_time = time.perf_counter()

        try:
            with torch.inference_mode():
                results = self.detector.predict(
                    image,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    imgsz=self.detector_imgsz,
                    max_det=self.max_det,
                    half=self.use_half,
                    verbose=False,
                    device=self.device,
                )
                if self.device.startswith("cuda"):
                    torch.cuda.synchronize()

            plates = []
            if results and results[0].boxes is not None:
                for index, box in enumerate(results[0].boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    plates.append({
                        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                        "confidence": conf,
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

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def ocr_plate(self, plate_image: np.ndarray) -> Tuple[str, float]:
        """OCR vùng biển số đã cắt và trả về văn bản cùng độ tin cậy."""
        start_time = time.perf_counter()

        try:
            with torch.inference_mode():
                results = self.ocr_model.predict(
                    plate_image,
                    conf=self.conf_threshold,
                    imgsz=self.ocr_imgsz,
                    max_det=max(self.max_det * 4, 8),
                    half=self.use_half,
                    verbose=False,
                    device=self.device,
                )
                if self.device.startswith("cuda"):
                    torch.cuda.synchronize()

            if results and hasattr(results[0], "boxes") and results[0].boxes is not None:
                detections = []
                for box in results[0].boxes:
                    x1, _, _, _ = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    detections.append({
                        "x": x1,
                        "class": cls,
                        "conf": conf,
                    })

                detections.sort(key=lambda item: item["x"])
                plate_text = self._decode_plate(detections)
                avg_conf = np.mean([item["conf"] for item in detections]) if detections else 0.0

                elapsed = time.perf_counter() - start_time
                self.metrics["ocr_time"].append(elapsed)
                self.metrics["ocr_count"] += 1
                logger.debug("OCR '%s' trong %.1fms", plate_text, elapsed * 1000)
                return plate_text, float(avg_conf)

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
