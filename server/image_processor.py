"""
════════════════════════════════════════════════════════════════════════════════
  IMAGE PROCESSOR SCRIPT v6.0
  Upload images → detect vehicles → OCR → save to database
  Luồng dữ liệu thật: Camera ảnh → AI xử lý → DB lưu → API trả → Frontend hiển thị
════════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ImageProcessor")

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════
DB_PATH = Path(__file__).parent / "traffic_ai.db"
UPLOADS_DIR = Path(__file__).parent.parent / "imge"

# Create directories
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ════════════════════════════════════════════════════════════════
# IMAGE PROCESSOR CLASS
# ════════════════════════════════════════════════════════════════
class ImageProcessor:
    """
    Process images từ camera/ESP32 → detect → OCR → save DB
    
    Thực tế workflow:
    1. Nhận ảnh từ camera (input)
    2. Detect vehicles bằng YOLO
    3. Check ROI (stop line)
    4. OCR đọc license plate
        5. Lưu file ảnh gốc
        7. Insert vào DB
    """
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.violation_count = 0
    
    def get_db(self):
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def save_image_file(self, image_path_input, output_dir, filename):
        """
        Copy image từ input → output directory
        
        Args:
            image_path_input: Đường dẫn ảnh gốc từ camera
            output_dir: Thư mục lưu ảnh thật trong imge/
            filename: Tên file output
        
        Returns:
            Đường dẫn tương đối (để lưu DB)
        """
        try:
            import shutil
            
            input_path = Path(image_path_input)
            if not input_path.exists():
                log.warning(f"Image file not found: {input_path}")
                return None
            
            output_path = output_dir / filename
            shutil.copy2(input_path, output_path)
            
            # Return relative URL path (for frontend)
            rel_path = f"/imge/{filename}"
            log.info(f"✓ Saved: {rel_path}")
            return rel_path
        
        except Exception as e:
            log.error(f"Failed to save image: {e}")
            return None
    
    def detect_vehicle_and_plate(self, image_path):
        """
        Detect vehicle + read plate (simulation)
        
        Trong thực tế:
        - Dùng YOLO detect
        - Dùng EasyOCR read plate
        
        Cho testing: Return mock data
        """
        try:
            import cv2
            
            image = cv2.imread(str(image_path))
            if image is None:
                return None, None, "CAR", 0.9, "UNKNOWN", 0.5
            
            h, w = image.shape[:2]
            
            # Mock: Simulate detection
            vehicle_type = "CAR" if hash(image_path) % 2 == 0 else "MOTORBIKE"
            vehicle_conf = 0.85 + (hash(image_path) % 15) / 100
            plate_text = self._mock_plate_text()
            plate_conf = 0.80 + (hash(image_path) % 20) / 100
            
            # Simulate plate crop (dùng bottom center area)
            roi_y = int(h * 0.72)  # 72% from top
            crop_y1 = max(0, roi_y - 20)
            crop_y2 = min(h, h)
            crop_x1 = max(0, w // 3)
            crop_x2 = min(w, 2 * w // 3)
            
            plate_crop = image[crop_y1:crop_y2, crop_x1:crop_x2]
            
            return image, plate_crop, vehicle_type, vehicle_conf, plate_text, plate_conf
        
        except Exception as e:
            log.error(f"Detection failed: {e}")
            return None, None, None, 0, None, 0
    
    def _mock_plate_text(self):
        """Generate mock plate number"""
        plates = self._mock_plate_catalog()
        import random
        return random.choice(plates)

    def _mock_plate_catalog(self):
        """Reference catalog for sample lookup/testing only."""
        return [
            "49-E1 999.66",
            "29-Y3 036.58",
            "70-F1 666.66",
            "97-H6 301.22",
            "59-V2 544.11",
            "51-G1 654.32",
        ]
    
    def save_violation_to_db(self, 
                           plate_text,
                           plate_confidence,
                           vehicle_type,
                           vehicle_confidence,
                           light_state,
                           full_image_path,
                           plate_image_path,
                           camera_id="CAM_01",
                           esp32_id="ESP32_MAIN",
                           speed_kmh=0.0):
        """
        Insert violation record vào database
        
        Cấu trúc record:
        {
            plate_text: "49-E1 999.66",
            plate_confidence: 0.92,
            vehicle_type: "CAR",
            light_state: "RED",
            full_image_path: "/imge/49_E1_999_66_1741617321.jpg",
            plate_image_path: "/imge/49_E1_999_66_1741617321.jpg",
            camera_id: "CAM_01",
            esp32_id: "ESP32_MAIN",
            violation_ts: 1678345421,
            status: "NEW"
        }
        """
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            
            violation_ts = int(datetime.now().timestamp())
            
            cursor.execute("""
                INSERT INTO violations 
                (plate_text, plate_confidence, vehicle_type, light_state,
                 speed_kmh, full_image_path, plate_image_path,
                 camera_id, esp32_id, violation_ts, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                plate_text,
                plate_confidence,
                vehicle_type,
                light_state,
                speed_kmh,
                full_image_path,
                plate_image_path,
                camera_id,
                esp32_id,
                violation_ts,
                "NEW"
            ))
            
            violation_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            self.violation_count += 1
            log.info(f"✅ Saved violation ID={violation_id}: {plate_text}")
            
            return violation_id
        
        except Exception as e:
            log.error(f"Failed to save to DB: {e}")
            return None
    
    def process_image(self, image_path, light_state="RED", camera_id="CAM_01"):
        """
        Process single image từ camera
        
        Workflow thực tế:
        1. Nhận ảnh từ camera
        2. Detect vehicles (YOLO)
        3. OCR license plate
        4. Lưu file ảnh
        5. Insert vào DB
        
        Args:
            image_path: Đường dẫn ảnh gốc từ camera
            light_state: RED/YELLOW/GREEN
            camera_id: Camera nào ghi nhận
        
        Returns:
            Violation ID if success
        """
        log.info(f"\n📷 Processing: {image_path}")
        log.info(f"   Light: {light_state} | Camera: {camera_id}")
        
        # Validate
        if not Path(image_path).exists():
            log.error(f"Image not found: {image_path}")
            return None
        
        if light_state != "RED":
            log.warning(f"Light is {light_state} - skipping (only process RED)")
            return None
        
        # Detect vehicle + plate
        full_img, plate_crop, vtype, vconf, plate, pconf = \
            self.detect_vehicle_and_plate(image_path)
        
        if not plate:
            log.error("Detection failed")
            return None
        
        # Generate filenames
        violation_id = self._get_next_violation_id()
        safe_plate = "".join(ch if ch.isalnum() else "_" for ch in (plate or "UNKNOWN").upper()).strip("_") or f"VIOLATION_{violation_id}"
        full_filename = f"{safe_plate}_{int(datetime.now().timestamp())}.jpg"
        
        # Save original captured image only. Plate-crop file generation is disabled.
        full_url = self.save_image_file(image_path, UPLOADS_DIR, full_filename)
        plate_url = full_url
        
        if not full_url:
            log.error("Failed to save images")
            return None
        
        # Save to database
        violation_id = self.save_violation_to_db(
            plate_text=plate,
            plate_confidence=pconf,
            vehicle_type=vtype,
            vehicle_confidence=vconf,
            light_state=light_state,
            full_image_path=full_url,
            plate_image_path=plate_url or full_url,
            camera_id=camera_id,
            speed_kmh=0.0
        )
        
        return violation_id
    
    def _get_next_violation_id(self):
        """Get next violation ID"""
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(id) FROM violations")
            result = cursor.fetchone()[0]
            conn.close()
            return (result or 0) + 1
        except:
            return 1
    
    def process_batch(self, image_dir, light_state="RED", camera_id="CAM_01"):
        """Process all images in directory"""
        image_dir = Path(image_dir)
        if not image_dir.exists():
            log.error(f"Directory not found: {image_dir}")
            return 0
        
        images = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png"))
        log.info(f"\n📂 Found {len(images)} images in {image_dir}")
        
        success = 0
        for image_path in images:
            violation_id = self.process_image(
                str(image_path),
                light_state=light_state,
                camera_id=camera_id
            )
            if violation_id:
                success += 1
        
        log.info(f"\n✅ Processed: {success}/{len(images)} images")
        return success

# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Process images → detect → OCR → save DB"
    )
    
    parser.add_argument(
        "image_path",
        help="Image file or directory path"
    )
    
    parser.add_argument(
        "--light",
        default="RED",
        choices=["RED", "YELLOW", "GREEN"],
        help="Traffic light state (default: RED)"
    )
    
    parser.add_argument(
        "--camera",
        default="CAM_01",
        help="Camera ID (default: CAM_01)"
    )
    
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process all images in directory"
    )
    
    args = parser.parse_args()
    
    log.info("=" * 70)
    log.info("  IMAGE PROCESSOR — Real-time Violation Detection")
    log.info("  Camera → AI Processing → Database Saving")
    log.info("=" * 70)
    
    processor = ImageProcessor()
    
    image_path = Path(args.image_path)
    
    if args.batch or image_path.is_dir():
        processor.process_batch(
            image_path,
            light_state=args.light,
            camera_id=args.camera
        )
    else:
        processor.process_image(
            str(image_path),
            light_state=args.light,
            camera_id=args.camera
        )
    
    log.info("\n" + "=" * 70)
    log.info(f"✅ COMPLETE: {processor.violation_count} violations saved")
    log.info("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\n⛔ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        log.error(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
