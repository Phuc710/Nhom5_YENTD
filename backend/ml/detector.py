"""
YOLO License Plate Detection Service (PRODUCTION)
"""
from ultralytics import YOLO
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from config.settings import settings
from utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_fixed
import os
import time
import torch

logger = get_logger(__name__)

class LicensePlateDetector:
    def __init__(self):
        """Initialize YOLO models with GPU support"""
        # GPU setup
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"🚀 Initializing detector on device: {self.device}")
        
        # Load models
        detector_path = os.path.join(os.path.dirname(__file__), settings.detector_model_path)
        ocr_path = os.path.join(os.path.dirname(__file__), settings.ocr_model_path)
        
        logger.info(f"📦 Loading detection model: {detector_path}")
        self.detector = YOLO(detector_path)
        self.detector.to(self.device)
        
        logger.info(f"📦 Loading OCR model: {ocr_path}")
        self.ocr_model = YOLO(ocr_path)
        self.ocr_model.to(self.device)
        
        self.conf_threshold = settings.confidence_threshold
        self.iou_threshold = settings.iou_threshold
        
        # Metrics tracking
        self.metrics = {
            "detection_time": [],
            "ocr_time": [],
            "detection_count": 0,
            "ocr_count": 0,
            "errors": 0
        }
        
        # Vietnam character mapping (PRODUCTION)
        self.char_map = {
            # Numbers
            0: '0', 1: '1', 2: '2', 3: '3', 4: '4', 
            5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
            # Letters (Vietnam plates - no I, J, O, Q, R, W)
            10: 'A', 11: 'B', 12: 'C', 13: 'D', 14: 'E',
            15: 'F', 16: 'G', 17: 'H', 18: 'K', 19: 'L',
            20: 'M', 21: 'N', 22: 'P', 23: 'S', 24: 'T',
            25: 'U', 26: 'V', 27: 'X', 28: 'Y', 29: 'Z',
            # Special characters
            30: '-',
            31: '.'
        }
        
        logger.info("✅ Detector initialized successfully")
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def detect_plates(self, image: np.ndarray) -> List[Dict]:
        """
        Detect license plates in image with retry
        Returns: List of detected plates with bounding boxes
        """
        start_time = time.time()
        
        try:
            results = self.detector.predict(
                image,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                verbose=False,
                device=self.device
            )
            
            plates = []
            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for i, box in enumerate(boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    
                    plates.append({
                        'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                        'confidence': conf,
                        'plate_index': i
                    })
            
            # Metrics
            elapsed = time.time() - start_time
            self.metrics["detection_time"].append(elapsed)
            self.metrics["detection_count"] += len(plates)
            
            logger.info(f"🔍 Detected {len(plates)} plate(s) in {elapsed*1000:.1f}ms")
            return plates
            
        except Exception as e:
            self.metrics["errors"] += 1
            logger.error(f"❌ Detection failed: {e}")
            raise
    
    def crop_plate(self, image: np.ndarray, bbox: Dict) -> np.ndarray:
        """Crop plate region from image"""
        x1, y1, x2, y2 = bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2']
        return image[y1:y2, x1:x2]
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def ocr_plate(self, plate_image: np.ndarray) -> Tuple[str, float]:
        """
        Perform OCR on cropped plate image with retry
        Returns: (plate_text, confidence)
        """
        start_time = time.time()
        
        try:
            results = self.ocr_model.predict(
                plate_image,
                conf=self.conf_threshold,
                verbose=False,
                device=self.device
            )
            
            if len(results) > 0 and hasattr(results[0], 'boxes') and results[0].boxes is not None:
                # Get all detected characters and sort by x position
                detections = []
                boxes = results[0].boxes
                
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    
                    detections.append({
                        'x': x1,
                        'class': cls,
                        'conf': conf
                    })
                
                # Sort by x position (left to right)
                detections.sort(key=lambda x: x['x'])
                
                # Decode plate text
                plate_text = self._decode_plate(detections)
                avg_conf = np.mean([d['conf'] for d in detections]) if detections else 0.0
                
                # Metrics
                elapsed = time.time() - start_time
                self.metrics["ocr_time"].append(elapsed)
                self.metrics["ocr_count"] += 1
                
                logger.info(f"📝 OCR: '{plate_text}' (conf: {avg_conf:.2f}) in {elapsed*1000:.1f}ms")
                return plate_text, float(avg_conf)
            
            logger.warning("⚠️ No characters detected in plate")
            return "", 0.0
            
        except Exception as e:
            self.metrics["errors"] += 1
            logger.error(f"❌ OCR failed: {e}")
            raise
    
    def _decode_plate(self, detections: List[Dict]) -> str:
        """Decode plate text from class detections"""
        chars = []
        for d in detections:
            char = self.char_map.get(d['class'], '?')
            if char == '?':
                logger.warning(f"⚠️ Unknown class ID: {d['class']}")
            chars.append(char)
        
        return ''.join(chars)
    
    def process_image(self, image_path: str) -> List[Dict]:
        """
        Full pipeline: detect plates + OCR
        Returns: List of detected plates with text
        """
        try:
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"❌ Cannot read image: {image_path}")
                raise ValueError(f"Cannot read image: {image_path}")
            
            logger.info(f"🖼️ Processing image: {image_path}")
            
            # Detect plates
            plates = self.detect_plates(image)
            
            if not plates:
                logger.info("ℹ️ No plates detected")
                return []
            
            # OCR each plate
            results = []
            for plate in plates:
                try:
                    # Crop plate region
                    plate_img = self.crop_plate(image, plate['bbox'])
                    
                    # Perform OCR
                    plate_text, ocr_conf = self.ocr_plate(plate_img)
                    
                    results.append({
                        'bbox': plate['bbox'],
                        'detection_confidence': plate['confidence'],
                        'plate_text': plate_text,
                        'ocr_confidence': ocr_conf,
                        'overall_confidence': (plate['confidence'] + ocr_conf) / 2,
                        'confidence': ocr_conf  # For compatibility
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Failed to process plate {plate['plate_index']}: {e}")
                    continue
            
            logger.info(f"✅ Processed {len(results)}/{len(plates)} plate(s)")
            return results
            
        except Exception as e:
            logger.error(f"❌ Image processing failed: {e}")
            return []
    
    def get_metrics(self) -> Dict:
        """Get performance metrics"""
        return {
            "avg_detection_time_ms": np.mean(self.metrics["detection_time"]) * 1000 if self.metrics["detection_time"] else 0,
            "avg_ocr_time_ms": np.mean(self.metrics["ocr_time"]) * 1000 if self.metrics["ocr_time"] else 0,
            "total_detections": self.metrics["detection_count"],
            "total_ocr": self.metrics["ocr_count"],
            "total_errors": self.metrics["errors"],
            "device": self.device
        }

# Singleton instance
_detector_instance: Optional[LicensePlateDetector] = None

def get_detector() -> LicensePlateDetector:
    """Get or create detector instance"""
    global _detector_instance
    if _detector_instance is None:
        logger.info("🔧 Creating detector instance")
        _detector_instance = LicensePlateDetector()
    return _detector_instance
