
import cv2
import numpy as np
import torch
import os
import time
import threading
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

from backend.config.settings import settings

try:
    import backend.function.utils_rotate as utils_rotate
except ImportError:
    utils_rotate = None

try:
    import backend.function.helper as helper
except ImportError:
    helper = None

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class LicensePlateDetector:
    DEFAULT_DETECTOR_CONF = 0.4
    DEFAULT_OCR_CONF = 0.5
    MAX_FRAME_WIDTH_RESIZE = 1280
    MIN_PLATE_WIDTH_OCR = 100
    PLATE_CROP_PADDING = 5
    MIN_AREA_THRESHOLD = 1000
    CACHE_TIMEOUT = 2.0

    def __init__(
        self,
        detector_model_path: Optional[str] = None,
        ocr_model_path: Optional[str] = None,
    ):
        self.device = self._resolve_device()
        self.conf_threshold = float(
            getattr(settings, "confidence_threshold", self.DEFAULT_DETECTOR_CONF) or self.DEFAULT_DETECTOR_CONF
        )
        self.ocr_conf_threshold = self.DEFAULT_OCR_CONF
        self.use_half = bool(settings.ml_use_half and self.device.startswith("cuda"))

        self.detector_model_path = detector_model_path or settings.detector_model_path
        self.ocr_model_path = ocr_model_path or settings.ocr_model_path
        
        self.yolo_LP_detect = None
        self.yolo_license_plate = None
        self.processing_lock = threading.Lock()
        self.models_loaded = False
        self.plate_cache = {}

        self.load_models()

        if settings.ml_warmup_runs > 0:
            self._warmup()

    def _resolve_device(self) -> str:
        requested = str(settings.ml_device or "auto").strip().lower()
        if requested in {"auto", ""}:
            # torch.hub (YOLOv5) may reject 'cuda' as an invalid device string.
            # Use a safe device string that YOLOv5 accepts ('0' for first GPU) and fall back to CPU.
            if torch.cuda.is_available():
                try:
                    # Confirm CUDA is usable by creating a tensor on the GPU
                    torch.zeros(1).to('cuda')
                    return '0'
                except Exception:
                    logger.warning('CUDA reported available but is not usable; falling back to CPU.')
            return "cpu"
        
        # If user explicitly configured something, try to clean "cuda" -> "0" for yolov5 torch hub compatibility
        if requested == "cuda":
            return "0"
        return requested

    def load_models(self) -> bool:
        if self.models_loaded:
            return True

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                
                # Load detector model
                if os.path.exists(self.detector_model_path):
                    logger.info("Nạp mô hình phát hiện biển số: %s (yolov5 hub)", self.detector_model_path)
                    self.yolo_LP_detect = torch.hub.load(
                        'ultralytics/yolov5', 'custom',
                        path=self.detector_model_path,
                        force_reload=False,
                        device=self.device,
                        trust_repo=True
                    )
                    self.yolo_LP_detect.conf = self.conf_threshold
                else:
                    logger.warning("Không tìm thấy %s, dùng yolov5s mặc định", self.detector_model_path)
                    self.yolo_LP_detect = torch.hub.load('ultralytics/yolov5', 'yolov5s', device=self.device, trust_repo=True)
                    self.yolo_LP_detect.conf = 0.3

                # Load OCR model
                if os.path.exists(self.ocr_model_path):
                    logger.info("Nạp mô hình OCR biển số: %s (yolov5 hub)", self.ocr_model_path)
                    self.yolo_license_plate = torch.hub.load(
                        'ultralytics/yolov5', 'custom',
                        path=self.ocr_model_path,
                        force_reload=False,
                        device=self.device,
                        trust_repo=True
                    )
                    self.yolo_license_plate.conf = self.ocr_conf_threshold
                else:
                    logger.warning("Không tìm thấy model OCR: %s", self.ocr_model_path)

            self.models_loaded = True
            return True

        except Exception as e:
            logger.error(f"Không thể nạp mô hình: {e}")
            return False

    def _warmup(self) -> None:
        """Làm nóng CUDA/context để request đầu tiên không bị khựng."""
        if os.getenv("SKIP_WARMUP") or not self.models_loaded:
            return
        
        try:
            dummy_frame = np.zeros((settings.ml_detector_imgsz, settings.ml_detector_imgsz, 3), dtype=np.uint8)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for _ in range(max(int(settings.ml_warmup_runs), 1)):
                    if self.yolo_LP_detect:
                        _ = self.yolo_LP_detect(dummy_frame, size=settings.ml_detector_imgsz)
                    
                    if self.yolo_license_plate:
                        dummy_plate = np.zeros((settings.ml_ocr_imgsz, settings.ml_ocr_imgsz, 3), dtype=np.uint8)
                        _ = self.yolo_license_plate(dummy_plate, size=settings.ml_ocr_imgsz)
                
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            logger.info("Đã warmup mô hình %s lần", settings.ml_warmup_runs)
        except Exception as exc:
            logger.warning("Warmup mô hình thất bại, tiếp tục chạy thường: %s", exc)

    def preprocess_frame(self, frame: np.ndarray, config: Optional[Dict] = None) -> np.ndarray:
        if frame is None or frame.size == 0:
            return frame

        try:
            # Orientation: use config or fallback to global settings
            rotate_180 = config.get("rotate_180", settings.ml_rotate_180) if config else settings.ml_rotate_180
            flip_horizontal = config.get("flip_horizontal", settings.ml_flip_horizontal) if config else settings.ml_flip_horizontal

            if rotate_180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            
            if flip_horizontal:
                frame = cv2.flip(frame, 1)

            height, width = frame.shape[:2]
            
            if width > self.MAX_FRAME_WIDTH_RESIZE:
                scale = self.MAX_FRAME_WIDTH_RESIZE / width
                new_width = self.MAX_FRAME_WIDTH_RESIZE
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced_frame = cv2.merge([l, a, b])
            enhanced_frame = cv2.cvtColor(enhanced_frame, cv2.COLOR_LAB2BGR)

            return enhanced_frame
        except Exception as e:
            logger.error(f"Lỗi khi tiền xử lý khung hình: {e}")
            return frame

    def process_frame(self, image: np.ndarray, config: Optional[Dict] = None) -> List[Dict]:
        """
        Chạy trọn pipeline detect + OCR trên ảnh đã giải mã sẵn.
        Đây là hàm interface tiêu chuẩn để tương thích với backend cũ.
        """
        result = self.detect_and_read_plate(image, config=config)
        if not result.get("success"):
            return []

        formatted_plates = []
        for plate in result.get("plates", []):
            x1, y1, x2, y2 = plate["bbox"]
            formatted_plates.append({
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "detection_confidence": plate["confidence"],
                "plate_text": plate["text"],
                "ocr_confidence": plate["confidence"],
                "overall_confidence": plate["confidence"],
                "confidence": plate["confidence"],
            })
            
        return formatted_plates

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

    def process_image_file(self, image_path: str) -> Dict:
        if not os.path.exists(image_path):
            return {"success": False, "plates": [], "error": f"Không tìm thấy tệp ảnh: {image_path}"}

        frame = cv2.imread(image_path)
        if frame is None:
            return {"success": False, "plates": [], "error": f"Không thể nạp ảnh: {image_path}"}

        return self.detect_and_read_plate(frame)

    def get_metrics(self) -> Dict:
        """Trả về thống kê (stub để giữ tương thích)."""
        return {
            "avg_detection_time_ms": 0.0,
            "avg_ocr_time_ms": 0.0,
            "total_detections": 0,
            "total_ocr": 0,
            "total_errors": 0,
            "device": self.device,
            "half_precision": self.use_half,
            "cached_plates": len(self.plate_cache),
        }

    def get_best_plate(self, detection_result: Dict) -> Optional[Dict]:
        if not detection_result.get("success") or not detection_result.get("plates"):
            return None
        return detection_result["plates"][0]

    def is_ready(self) -> bool:
        return self.models_loaded

    def detect_and_read_plate(self, frame: np.ndarray, config: Optional[Dict] = None) -> dict:
        if not self.models_loaded:
            return {'success': False, 'plates': [], 'error': "Mô hình chưa được nạp"}

        if frame is None or frame.size == 0:
            return {'success': False, 'plates': [], 'error': "Khung hình đầu vào trống"}

        with self.processing_lock:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    
                    processed_frame = self.preprocess_frame(frame, config=config)
                    frame_hash = hash(processed_frame.tobytes())

                    # Update conf threshold dynamically if changed by UI
                    target_conf = config.get("confidence_threshold", self.conf_threshold) if config else self.conf_threshold
                    if self.yolo_LP_detect.conf != target_conf:
                        self.yolo_LP_detect.conf = target_conf

                    plates_data = self.yolo_LP_detect(processed_frame, size=settings.ml_detector_imgsz)
                    detections = plates_data.xyxy[0].cpu().numpy()
                
                if detections.size == 0:
                    return {'success': False, 'plates': [], 'error': "Không phát hiện thấy biển số xe"}

                detected_plates = []
                plates_with_area = [(plate, (plate[2] - plate[0]) * (plate[3] - plate[1])) 
                                  for plate in detections 
                                  if (plate[2] - plate[0]) * (plate[3] - plate[1]) > self.MIN_AREA_THRESHOLD]
                
                plates_with_area.sort(key=lambda x: x[1], reverse=True)
                
                for plate, area in plates_with_area[:2]:
                    x1, y1, x2, y2, conf, cls = plate
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                    if x2 <= x1 or y2 <= y1:
                        continue

                    cache_key = f"{frame_hash}_{x1}_{y1}_{x2}_{y2}"
                    if cache_key in self.plate_cache:
                        cached_result, timestamp = self.plate_cache[cache_key]
                        if time.time() - timestamp < self.CACHE_TIMEOUT:
                            detected_plates.append({
                                'bbox': (x1, y1, x2, y2),
                                'text': cached_result,
                                'confidence': float(conf),
                                'cached': True
                            })
                            continue

                    x1_crop = max(0, x1 - self.PLATE_CROP_PADDING)
                    y1_crop = max(0, y1 - self.PLATE_CROP_PADDING)
                    x2_crop = min(processed_frame.shape[1], x2 + self.PLATE_CROP_PADDING)
                    y2_crop = min(processed_frame.shape[0], y2 + self.PLATE_CROP_PADDING)

                    crop_img = processed_frame[y1_crop:y2_crop, x1_crop:x2_crop]

                    if crop_img.size == 0:
                        continue

                    plate_text = self.read_plate_optimized(crop_img)

                    if plate_text and plate_text != "unknown" and len(plate_text) > 3:
                        self.plate_cache[cache_key] = (plate_text, time.time())
                        detected_plates.append({
                            'bbox': (x1, y1, x2, y2),
                            'text': plate_text,
                            'confidence': float(conf),
                            'cropped_image': crop_img,
                            'cached': False
                        })

                detected_plates.sort(key=lambda x: x['confidence'], reverse=True)
                return {'success': len(detected_plates) > 0, 'plates': detected_plates, 'error': None}

            except Exception as e:
                logger.error(f"Lỗi khi thực hiện nhận diện: {e}")
                return {'success': False, 'plates': [], 'error': str(e)}

    def read_plate_optimized(self, crop_img: np.ndarray) -> str:
        if crop_img is None or crop_img.size == 0:
            return "unknown"

        try:
            if self.yolo_license_plate is not None and helper is not None:
                height, width = crop_img.shape[:2]
                if width < self.MIN_PLATE_WIDTH_OCR and width > 0:
                    scale = self.MIN_PLATE_WIDTH_OCR / width
                    new_width = self.MIN_PLATE_WIDTH_OCR
                    new_height = int(height * scale)
                    crop_img = cv2.resize(crop_img, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

                plate_text = helper.read_plate(self.yolo_license_plate, crop_img)
                if plate_text and plate_text != "unknown" and len(plate_text) > 3:
                    return plate_text

            return self.tesseract_ocr(crop_img)

        except Exception as e:
            logger.error(f"Lỗi khi xử lý OCR: {e}")
            return "unknown"

    def tesseract_ocr(self, crop_img: np.ndarray) -> str:
        if not TESSERACT_AVAILABLE or crop_img is None or crop_img.size == 0:
            return "unknown"

        try:
            gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            text = pytesseract.image_to_string(thresh, config=custom_config).strip()
            
            if len(text) >= 4 and text.replace(' ', '').isalnum():
                return text.replace(' ', '').upper()
            
            return "unknown"

        except Exception:
            return "unknown"

    def clear_cache(self):
        self.plate_cache.clear()


_detector_instance: Optional[LicensePlateDetector] = None


def get_detector() -> LicensePlateDetector:
    """Lấy singleton detector để tái sử dụng model đã nạp."""
    global _detector_instance
    if _detector_instance is None:
        logger.info("Tạo mới singleton detector")
        _detector_instance = LicensePlateDetector()
    return _detector_instance
