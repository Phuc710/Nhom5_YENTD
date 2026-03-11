"""
════════════════════════════════════════════════════════════════════════════════
  SEED DATABASE SCRIPT v6.0
  Tạo sample violations data từ license plate thực tế cho testing
  Chuẩn theo yêu cầu thực tế: ảnh gốc + crop license plate
════════════════════════════════════════════════════════════════════════════════
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════
DB_PATH = Path(__file__).parent / "traffic_ai.db"
UPLOADS_DIR = Path(__file__).parent.parent / "imge"
VIOLATIONS_DIR = UPLOADS_DIR / "violations"
PLATES_DIR = UPLOADS_DIR / "plates"

# Sample data từ images bạn gửi
SAMPLE_VIOLATIONS = [
    {
        "plate": "49-E1 999.66",
        "vehicle_type": "CAR",
        "light": "RED",
        "speed": 15.5,
        "confidence": 0.92,
        "camera": "CAM_01"
    },
    {
        "plate": "29-Y3 036.58",
        "vehicle_type": "MOTORBIKE",
        "light": "RED",
        "speed": 18.2,
        "confidence": 0.88,
        "camera": "CAM_01"
    },
    {
        "plate": "70-F1 666.66",
        "vehicle_type": "CAR",
        "light": "RED",
        "speed": 12.8,
        "confidence": 0.95,
        "camera": "CAM_02"
    },
    {
        "plate": "97-H6 301.22",
        "vehicle_type": "MOTORBIKE",
        "light": "RED",
        "speed": 20.1,
        "confidence": 0.85,
        "camera": "CAM_02"
    },
    {
        "plate": "59-V2 544.11",
        "vehicle_type": "CAR",
        "light": "RED",
        "speed": 14.3,
        "confidence": 0.91,
        "camera": "CAM_01"
    },
    {
        "plate": "51-G1 654.32",
        "vehicle_type": "MOTORBIKE",
        "light": "RED",
        "speed": 19.5,
        "confidence": 0.87,
        "camera": "CAM_02"
    },
]

# Sample devices
SAMPLE_DEVICES = [
    {
        "device_id": "esp32_cam_1",
        "device_name": "ESP32-CAM #1",
        "device_type": "CAMERA",
        "is_online": 1,
    },
    {
        "device_id": "esp32_cam_2",
        "device_name": "ESP32-CAM #2",
        "device_type": "CAMERA",
        "is_online": 1,
    },
    {
        "device_id": "esp32_main",
        "device_name": "ESP32 Main",
        "device_type": "ESP32_MAIN",
        "is_online": 1,
    },
    {
        "device_id": "esp32_led",
        "device_name": "LED 7-Segment",
        "device_type": "LED_7SEG",
        "is_online": 1,
    },
]

# ════════════════════════════════════════════════════════════════
# FUNCTIONS
# ════════════════════════════════════════════════════════════════

def create_directories():
    """Create upload directories"""
    VIOLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    PLATES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ Directories created:")
    print(f"   - {VIOLATIONS_DIR}")
    print(f"   - {PLATES_DIR}")

def create_dummy_images():
    """Create placeholder images for violations"""
    import numpy as np
    import cv2
    
    print("\n📷 Creating placeholder images...")
    
    # Create dummy violation image (640x480 dark image with red border)
    violation_img = np.zeros((480, 640, 3), dtype=np.uint8)
    violation_img[:] = (30, 30, 30)  # Dark background
    cv2.rectangle(violation_img, (10, 10), (630, 470), (0, 0, 255), 3)  # Red border
    cv2.putText(violation_img, "VIOLATION", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 2)
    
    # Create dummy plate image (200x100 white image with text)
    plate_img = np.zeros((100, 200, 3), dtype=np.uint8)
    plate_img[:] = (240, 240, 240)  # Light background
    cv2.rectangle(plate_img, (5, 5), (195, 95), (0, 0, 0), 2)  # Black border
    cv2.putText(plate_img, "PLATE", (50, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    
    # Save sample images for each violation
    for i in range(1, len(SAMPLE_VIOLATIONS) + 1):
        vio_path = VIOLATIONS_DIR / f"v_{i}.jpg"
        plate_path = PLATES_DIR / f"p_{i}.jpg"
        
        cv2.imwrite(str(vio_path), violation_img)
        cv2.imwrite(str(plate_path), plate_img)
        print(f"   ✓ Created: {vio_path.name}, {plate_path.name}")

def seed_violations(conn):
    """Insert sample violations into database"""
    print("\n🚗 Inserting violations...")
    
    cursor = conn.cursor()
    now = datetime.now()
    
    for i, vio in enumerate(SAMPLE_VIOLATIONS, 1):
        # Vary timestamps (most recent first)
        violation_time = now - timedelta(minutes=i*5)
        violation_ts = int(violation_time.timestamp())
        
        cursor.execute("""
            INSERT INTO violations 
            (plate_text, plate_confidence, vehicle_type, light_state, 
             speed_kmh, full_image_path, plate_image_path, 
             camera_id, esp32_id, violation_ts, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            vio["plate"],
            vio["confidence"],
            vio["vehicle_type"],
            vio["light"],
            vio["speed"],
            f"/static/uploads/violations/v_{i}.jpg",
            f"/static/uploads/plates/p_{i}.jpg",
            vio["camera"],
            "ESP32_MAIN",
            violation_ts,
            "NEW"
        ))
        
        print(f"   ✓ {i}. {vio['plate']} | {vio['vehicle_type']} | {vio['light']} | {violation_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    conn.commit()
    print(f"✅ Inserted {len(SAMPLE_VIOLATIONS)} violations")

def seed_devices(conn):
    """Insert sample devices into database"""
    print("\n📱 Inserting devices...")
    
    cursor = conn.cursor()
    now = datetime.now()
    
    for device in SAMPLE_DEVICES:
        cursor.execute("""
            INSERT OR REPLACE INTO device_status 
            (device_id, device_name, device_type, is_online, 
             last_heartbeat, heartbeat_ts, signal_strength, cpu_temp_c, uptime_seconds)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
        """, (
            device["device_id"],
            device["device_name"],
            device["device_type"],
            device["is_online"],
            int(now.timestamp()),
            80 + (hash(device["device_id"]) % 20),  # 80-100% signal
            45 + (hash(device["device_id"]) % 15),  # 45-60°C
            3600 + (hash(device["device_id"]) % 86400)  # 1-24 hours uptime
        ))
        
        print(f"   ✓ {device['device_name']} ({device['device_type']}) - Online")
    
    conn.commit()
    print(f"✅ Inserted {len(SAMPLE_DEVICES)} devices")

def verify_data(conn):
    """Verify inserted data"""
    print("\n✔️  DATA VERIFICATION")
    print("════════════════════════════════════════════")
    
    cursor = conn.cursor()
    
    # Count violations
    cursor.execute("SELECT COUNT(*) FROM violations WHERE status != 'DELETED'")
    vio_count = cursor.fetchone()[0]
    print(f"\n📊 Violations: {vio_count} records")
    
    cursor.execute("SELECT id, plate_text, vehicle_type, light_state, violation_ts FROM violations ORDER BY violation_ts DESC LIMIT 3")
    for row in cursor.fetchall():
        ts = datetime.fromtimestamp(row[4]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"   - ID:{row[0]} | {row[1]} | {row[2]} | {row[3]} | {ts}")
    
    # Count devices
    cursor.execute("SELECT COUNT(*) FROM device_status WHERE is_online = 1")
    dev_count = cursor.fetchone()[0]
    print(f"\n📱 Devices Online: {dev_count} devices")
    
    cursor.execute("SELECT device_id, device_name, is_online FROM device_status")
    for row in cursor.fetchall():
        status = "🟢 Online" if row[2] else "🔴 Offline"
        print(f"   - {row[0]}: {row[1]} {status}")
    
    # Check image files
    print(f"\n🖼️  Image Files:")
    vio_files = list(VIOLATIONS_DIR.glob("v_*.jpg"))
    plate_files = list(PLATES_DIR.glob("p_*.jpg"))
    print(f"   - Violation images: {len(vio_files)} files")
    print(f"   - Plate images: {len(plate_files)} files")
    
    if vio_files:
        print(f"   - Location: {VIOLATIONS_DIR}")
    if plate_files:
        print(f"   - Location: {PLATES_DIR}")
    
    print("\n✅ Database is ready for testing!")

def main():
    """Main function"""
    print("=" * 70)
    print("  SEED DATABASE — AI Traffic Control v6.0")
    print("  Create sample violations + devices + images")
    print("=" * 70)
    
    try:
        # Check if database exists
        if not DB_PATH.exists():
            print(f"\n❌ ERROR: Database not found at {DB_PATH}")
            print("Run 'sqlite3 traffic_ai.db < schema.sql' first")
            return False
        
        # Create directories
        create_directories()
        
        # Create dummy images
        try:
            import cv2
            import numpy as np
            create_dummy_images()
        except ImportError:
            print("\n⚠️  OpenCV not installed - skipping image creation")
            print("Images will be created by AI engine when processing real violations")
        
        # Connect to database
        conn = sqlite3.connect(str(DB_PATH))
        
        # Seed data
        seed_violations(conn)
        seed_devices(conn)
        
        # Verify
        verify_data(conn)
        
        conn.close()
        
        print("\n" + "=" * 70)
        print("✅ SEEDING COMPLETE!")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Start Flask: python app.py")
        print("2. Open browser: http://localhost:5050")
        print("3. Check Dashboard → Violations")
        print("=" * 70 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)