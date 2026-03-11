"""
════════════════════════════════════════════════════════════════════════════════
  AI TRAFFIC ENGINE v7.0
  YOLOv8 Detection + EasyOCR + Real-time Processing
  Red-light violation detection — production-ready
════════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import cv2
import json
import time
import threading
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict, List
import numpy as np

# AI Libraries
try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False
    print("[WARN] ultralytics not installed - YOLO detection disabled")

try:
    import easyocr
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("[WARN] easyocr not installed - OCR disabled")

# ════════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("AIEngine")

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "yolov8n.pt"
UPLOADS_DIR = BASE_DIR.parent / "imge"
VIOLATIONS_DIR = UPLOADS_DIR / "violations"
PLATES_DIR = UPLOADS_DIR / "plates"

VIOLATIONS_DIR.mkdir(parents=True, exist_ok=True)
PLATES_DIR.mkdir(parents=True, exist_ok=True)

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════
CONFIG = {
    # Read API base URL from environment — allows running ai_engine against remote servers.
    # Default: localhost:5050 for same-machine development.
    "api_base": os.getenv("TRAFFIC_API_BASE", "http://localhost:5050/api"),
    "camera_id": os.getenv("CAMERA_ID", "CAM_01"),
    "esp32_id": os.getenv("ESP32_ID", "ESP32_MAIN"),
    "target_fps": 20,
    "yolo_conf": float(os.getenv("YOLO_CONF", "0.45")),
    "ocr_conf": float(os.getenv("OCR_CONF", "0.55")),
    "roi_y_ratio": 0.72,  # ROI zone: lower 72% of frame
    "violation_cooldown": float(os.getenv("VIOLATION_COOLDOWN", "3.0")),
    "frame_width": 640,
    "frame_height": 480,
}

# YOLO class mapping
YOLO_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

VEHICLE_TYPES = {
    "car": "CAR",
    "motorcycle": "MOTORBIKE",
    "bus": "BUS",
    "truck": "TRUCK",
}

# ════════════════════════════════════════════════════════════════
# AI ENGINE CLASS
# ════════════════════════════════════════════════════════════════
class AIEngine:
    """Real-time violation detection engine"""
    
    def __init__(self):
        self.running = False
        self.yolo = None
        self.ocr = None
        self.last_violation_ts = {}  # Track last violation per vehicle class
        self.frame_count = 0
        self.detection_count = 0
        self.violation_count = 0
        self.start_time = time.time()
        
        # Load models
        self._load_models()
    
    def _load_models(self):
        """Load YOLO and OCR models"""
        # Load YOLO
        if HAS_YOLO:
            try:
                if MODEL_PATH.exists():
                    self.yolo = YOLO(str(MODEL_PATH))
                    log.info(f"✅ YOLO loaded: {MODEL_PATH}")
                else:
                    log.warning(f"⚠️ YOLO model not found: {MODEL_PATH}")
            except Exception as e:
                log.error(f"❌ YOLO load failed: {e}")
        
        # Load OCR
        if HAS_OCR:
            try:
                self.ocr = easyocr.Reader(["en"], gpu=False)
                log.info("✅ EasyOCR loaded")
            except Exception as e:
                log.error(f"❌ OCR load failed: {e}")
    
    def detect_vehicles(self, frame) -> List[Dict]:
        """
        Detect vehicles in frame using YOLO
        Returns: List of detections
        """
        if not self.yolo:
            return []
        
        try:
            results = self.yolo(frame, conf=CONFIG["yolo_conf"], verbose=False)
            
            detections = []
            for result in results:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    if cls_id not in YOLO_CLASSES:
                        continue
                    
                    cls_name = YOLO_CLASSES[cls_id]
                    vehicle_type = VEHICLE_TYPES.get(cls_name, "UNKNOWN")
                    
                    # Bounding box
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    detections.append({
                        "cls_name": cls_name,
                        "vehicle_type": vehicle_type,
                        "confidence": confidence,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                    })
            
            return detections
        except Exception as e:
            log.error(f"[YOLO] Detection failed: {e}")
            return []
    
    def detect_plate(self, frame) -> Tuple[str, float]:
        """
        Detect and read license plate from frame
        Returns: (plate_text, confidence)
        """
        if not self.ocr:
            return "", 0.0
        
        try:
            results = self.ocr.readtext(frame, detail=1)  # detail=1 for confidence
            
            plate_text = ""
            max_conf = 0.0
            
            for (bbox, text, conf) in results:
                # Filter characters
                cleaned = "".join(
                    c for c in text.upper() 
                    if c.isalnum() or c in "-"
                )
                
                if len(cleaned) >= 3 and conf > CONFIG["ocr_conf"]:  # Minimum 3 chars
                    if conf > max_conf:
                        max_conf = conf
                        plate_text = cleaned
            
            return plate_text, max_conf
        except Exception as e:
            log.error(f"[OCR] Detection failed: {e}")
            return "", 0.0
    
    def check_roi(self, detection, frame_height) -> bool:
        """
        Check if detection is in ROI (stop line area)
        ROI = bottom 28% of frame (below y_ratio=0.72)
        """
        roi_y = int(frame_height * CONFIG["roi_y_ratio"])
        
        # Check if bottom of bbox is below ROI
        return detection["y2"] > roi_y
    
    def is_violation(self, detection, light_state: str) -> bool:
        """
        Check if detection is a violation
        Violation = vehicle in ROI + light is RED
        """
        if light_state != "RED":
            return False
        
        # Check cooldown (avoid duplicate detections)
        vtype = detection["vehicle_type"]
        now = time.time()
        last_ts = self.last_violation_ts.get(vtype, 0)
        
        if now - last_ts < CONFIG["violation_cooldown"]:
            return False
        
        self.last_violation_ts[vtype] = now
        return True
    
    def crop_plate_region(self, frame, detection) -> np.ndarray:
        """
        Crop region around detected vehicle to extract plate
        """
        x1, y1, x2, y2 = detection["x1"], detection["y1"], detection["x2"], detection["y2"]
        
        # Expand crop region for better plate capture
        h, w = frame.shape[:2]
        y1_crop = max(0, y1 + (y2 - y1) // 2)  # Start from middle of vehicle
        y2_crop = min(h, y2 + 30)  # Extend down a bit
        x1_crop = max(0, x1 - 20)
        x2_crop = min(w, x2 + 20)
        
        return frame[y1_crop:y2_crop, x1_crop:x2_crop]
    
    def save_violation_images(self, frame, plate_crop, plate_text: str, violation_id: int) -> Tuple[str, str]:
        """
        Save violation images to disk
        Returns: (full_image_url, plate_image_url)
        """
        try:
            # Save full violation image
            full_path = VIOLATIONS_DIR / f"v_{violation_id}.jpg"
            cv2.imwrite(str(full_path), frame)
            full_url = f"/static/uploads/violations/v_{violation_id}.jpg"
            
            # Save plate crop image
            plate_path = PLATES_DIR / f"p_{violation_id}.jpg"
            cv2.imwrite(str(plate_path), plate_crop)
            plate_url = f"/static/uploads/plates/p_{violation_id}.jpg"
            
            log.info(f"[IMG] Saved violation images: ID={violation_id}")
            return full_url, plate_url
        except Exception as e:
            log.error(f"[IMG] Save failed: {e}")
            return "", ""
    
    def upload_violation(self, violation_data: Dict):
        """
        Upload violation to Flask API
        """
        try:
            response = requests.post(
                f"{CONFIG['api_base']}/upload-violation",
                json=violation_data,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                violation_id = result.get("violation_id")
                log.info(f"[API] Violation uploaded: ID={violation_id}")
                return violation_id
            else:
                log.error(f"[API] Upload failed: {response.status_code}")
                return None
        except Exception as e:
            log.error(f"[API] Upload error: {e}")
            return None
    
    def process_frame(self, frame, light_state: str) -> Dict:
        """
        Process single frame
        Returns: stats dict
        """
        self.frame_count += 1
        h, w = frame.shape[:2]
        
        stats = {
            "frame_count": self.frame_count,
            "detections": 0,
            "violations": 0,
            "light_state": light_state
        }
        
        # Detect vehicles
        detections = self.detect_vehicles(frame)
        self.detection_count += len(detections)
        stats["detections"] = len(detections)
        
        # Check each detection
        for det in detections:
            # Check if in ROI
            if not self.check_roi(det, h):
                continue
            
            # Check if violation
            if not self.is_violation(det, light_state):
                continue
            
            # Crop plate region
            plate_crop = self.crop_plate_region(frame, det)
            
            # Read plate
            plate_text, plate_conf = self.detect_plate(plate_crop)
            
            # Save images
            violation_id = self.violation_count + 1
            full_url, plate_url = self.save_violation_images(frame, plate_crop, plate_text, violation_id)
            
            # Upload to API
            violation_data = {
                "plate": plate_text,
                "plate_confidence": plate_conf,
                "vehicle_type": det["vehicle_type"],
                "vehicle_confidence": det["confidence"],
                "light": light_state,
                "speed_kmh": 0.0,  # TODO: implement speed estimation
                "full_image_path": full_url,
                "plate_image_path": plate_url,
                "camera_id": CONFIG["camera_id"],
                "esp32_id": CONFIG["esp32_id"]
            }
            
            self.upload_violation(violation_data)
            self.violation_count += 1
            stats["violations"] += 1
            
            log.info(f"[VIOLATION] Plate: {plate_text} | Vehicle: {det['vehicle_type']} | Confidence: {plate_conf:.2f}")
        
        return stats
    
    def get_stats(self) -> Dict:
        """Get engine statistics"""
        uptime = time.time() - self.start_time
        fps = self.frame_count / uptime if uptime > 0 else 0
        
        return {
            "running": self.running,
            "uptime_seconds": int(uptime),
            "frame_count": self.frame_count,
            "detection_count": self.detection_count,
            "violation_count": self.violation_count,
            "fps": round(fps, 1),
            "models_loaded": {
                "yolo": self.yolo is not None,
                "ocr": self.ocr is not None
            }
        }

# ════════════════════════════════════════════════════════════════
# GLOBAL ENGINE INSTANCE
# ════════════════════════════════════════════════════════════════
ai_engine = AIEngine()

def start_ai(flask_app):
    """
    Start AI engine
    Called from Flask app
    """
    global ai_engine
    ai_engine.running = True
    log.info("✅ AI Engine started")
    return ai_engine

def process_violation(frame, light_state: str) -> Dict:
    """
    Process frame for violations
    Called from camera input or testing
    """
    if not ai_engine.running:
        return {"error": "Engine not running"}
    
    return ai_engine.process_frame(frame, light_state)

def get_ai_stats() -> Dict:
    """Get AI engine statistics"""
    return ai_engine.get_stats()

# ════════════════════════════════════════════════════════════════
# DEMO MODE (Testing)
# ════════════════════════════════════════════════════════════════
def demo_violation():
    """
    Generate demo violation for testing
    """
    demo_violation_data = {
        "plate": f"29A-{int(time.time()) % 100000:05d}",
        "plate_confidence": 0.92,
        "vehicle_type": "CAR",
        "vehicle_confidence": 0.95,
        "light": "RED",
        "speed_kmh": 15.5,
        "full_image_path": "/static/uploads/violations/demo.jpg",
        "plate_image_path": "/static/uploads/plates/demo.jpg",
        "camera_id": CONFIG["camera_id"],
        "esp32_id": CONFIG["esp32_id"]
    }
    
    ai_engine.upload_violation(demo_violation_data)
    log.info(f"[DEMO] Created violation: {demo_violation_data['plate']}")

if __name__ == "__main__":
    # Test mode
    ai_engine.running = True
    log.info("[TEST] AI Engine test mode")
    
    # Create demo violation
    demo_violation()
    
    # Print stats
    print(json.dumps(ai_engine.get_stats(), indent=2))