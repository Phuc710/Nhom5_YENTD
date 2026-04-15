"""
════════════════════════════════════════════════════════════════════════════════
  CSV IMPORTER SCRIPT v6.0
  Import violations data từ CSV → SQLite database
  Dùng để import dữ liệu lịch sử hoặc bulk testing
════════════════════════════════════════════════════════════════════════════════
"""

import csv
import sqlite3
import argparse
import logging
import os
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("CSVImporter")

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════
DB_PATH = Path(__file__).parent / "traffic_ai.db"
IMAGE_DIR = Path(__file__).parent.parent / "imge"
SAMPLE_CSV = Path(__file__).parent / "sample_violations.csv"
ALLOW_TEST_DATA = (os.getenv("TRAFFIC_ALLOW_TEST_DATA") or "0").strip().lower() in {"1", "true", "yes", "on"}

# CSV Column mapping
CSV_COLUMNS = {
    "plate_text": "Biển Số",
    "vehicle_type": "Loại Xe",
    "light_state": "Trạng Thái Đèn",
    "violation_time": "Thời Gian Vi Phạm",
    "full_image_path": "Ảnh Gốc",
    "plate_image_path": "Ảnh Biển Số",
    "camera_id": "Camera",
    "plate_confidence": "Độ Chính Xác OCR",
    "speed_kmh": "Tốc Độ (km/h)",
}

# ════════════════════════════════════════════════════════════════
# CSV IMPORTER CLASS
# ════════════════════════════════════════════════════════════════
class CSVImporter:
    """Import violations from CSV"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.imported_count = 0
        self.error_count = 0
    
    def get_db(self):
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _find_real_image_for_plate(self, plate: str) -> str:
        canon = "".join(ch for ch in (plate or "").upper() if ch.isalnum())
        for p in IMAGE_DIR.glob("*.*"):
            if not p.is_file() or p.name.lower() == "admin.jpg":
                continue
            if "".join(ch for ch in p.stem.upper() if ch.isalnum()) == canon:
                return f"/imge/{p.name}"
        return ""

    def normalize_plate(self, plate: str) -> str:
        if not plate:
            return ""
        text = plate.upper().strip().replace(" ", "").replace(".", "").replace("-", "")
        replace_map = {"O": "0", "I": "1", "L": "1", "Z": "2", "S": "5"}
        return "".join(replace_map.get(ch, ch) for ch in text if ch.isalnum())
    
    def parse_violation_time(self, time_str):
        """
        Parse violation time from various formats
        
        Supported formats:
        - "2026-03-10 14:35:21"
        - "2026-03-10T14:35:21"
        - "10/03/2026 14:35:21"
        """
        try:
            # Try ISO format
            if "T" in time_str:
                dt = datetime.fromisoformat(time_str)
            # Try MySQL format
            elif " " in time_str:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            # Try VN format
            elif "/" in time_str:
                dt = datetime.strptime(time_str, "%d/%m/%Y %H:%M:%S")
            else:
                dt = datetime.now()
            
            return dt, int(dt.timestamp())
        except Exception as e:
            log.warning(f"Failed to parse time '{time_str}': {e}")
            return datetime.now(), int(datetime.now().timestamp())
    
    def import_from_csv(self, csv_file, delimiter=",", allow_test_data: bool = False):
        """
        Import violations from CSV file
        
        CSV Format:
        plate_text,vehicle_type,light_state,violation_time,full_image_path,plate_image_path,camera_id,plate_confidence,speed_kmh
        49-E1 999.66,CAR,RED,2026-03-10 14:35:21,,,CAM_01,0.92,15.5
        29-Y3 036.58,MOTORBIKE,RED,2026-03-10 14:30:00,,,CAM_01,0.88,18.2
        """
        csv_path = Path(csv_file)
        if not csv_path.exists():
            log.error(f"CSV file not found: {csv_path}")
            return False
        if csv_path.resolve() == SAMPLE_CSV.resolve() and not allow_test_data:
            log.error("Blocked: sample_violations.csv is test-only. Use --allow-test-data to import.")
            return False
        
        log.info(f"\n📄 Reading CSV: {csv_path}")
        
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                
                if not reader.fieldnames:
                    log.error("CSV file is empty")
                    return False
                
                log.info(f"Columns: {', '.join(reader.fieldnames)}")
                
                for row_num, row in enumerate(reader, 2):  # Start from 2 (skip header)
                    try:
                        # Parse time
                        violation_time, violation_ts = self.parse_violation_time(
                            row.get("violation_time", str(datetime.now()))
                        )
                        
                        # Convert confidence to float
                        try:
                            plate_conf = float(row.get("plate_confidence", 0.0))
                        except:
                            plate_conf = 0.0
                        
                        try:
                            speed_kmh = float(row.get("speed_kmh", 0.0))
                        except:
                            speed_kmh = 0.0
                        
                        # Insert record
                        plate_text = row.get("plate_text") or row.get("plate") or "UNKNOWN"
                        image_path = row.get("image_path") or row.get("plate_image_path") or row.get("full_image_path") or self._find_real_image_for_plate(plate_text)
                        cursor.execute("""
                            INSERT INTO violations
                            (plate_text, plate_norm, plate_confidence, vehicle_type, light_state,
                             speed_kmh, full_image_path, plate_image_path,
                             camera_id, esp32_id, violation_ts, status, violation_reason)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            plate_text,
                            row.get("plate_norm") or self.normalize_plate(plate_text),
                            plate_conf,
                            row.get("vehicle_type", "CAR"),
                            row.get("light_state", "RED"),
                            speed_kmh,
                            image_path,
                            image_path,
                            row.get("camera_id", "CAM_01"),
                            row.get("esp32_id", "ESP32_MAIN"),
                            violation_ts,
                            "NEW",
                            row.get("violation_reason", "Vượt vạch dừng khi đèn đỏ"),
                        ))
                        
                        self.imported_count += 1
                        
                        if self.imported_count % 10 == 0:
                            log.info(f"  ✓ {self.imported_count} records imported...")
                    
                    except Exception as e:
                        log.error(f"Row {row_num}: {e}")
                        self.error_count += 1
            
            conn.commit()
            conn.close()
            
            return True
        
        except Exception as e:
            log.error(f"Failed to import CSV: {e}")
            return False
    
    def export_to_csv(self, output_file, limit=None):
        """
        Export violations to CSV
        
        Useful for: backup, analysis, sharing
        """
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            
            # Query violations
            if limit:
                query = "SELECT * FROM violations WHERE status != 'DELETED' ORDER BY violation_ts DESC LIMIT ?"
                cursor.execute(query, (limit,))
            else:
                query = "SELECT * FROM violations WHERE status != 'DELETED' ORDER BY violation_ts DESC"
                cursor.execute(query)
            
            rows = cursor.fetchall()
            
            if not rows:
                log.warning("No violations to export")
                return False
            
            # Write CSV
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ["id", "plate_text", "plate_confidence", "vehicle_type", 
                             "light_state", "speed_kmh", "violation_time", "violation_ts",
                             "full_image_path", "plate_image_path", "camera_id", "esp32_id", "status"]
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for row in rows:
                    # Convert timestamp to datetime string
                    violation_time = datetime.fromtimestamp(row["violation_ts"]).isoformat()
                    
                    writer.writerow({
                        "id": row["id"],
                        "plate_text": row["plate_text"],
                        "plate_confidence": row["plate_confidence"],
                        "vehicle_type": row["vehicle_type"],
                        "light_state": row["light_state"],
                        "speed_kmh": row["speed_kmh"],
                        "violation_time": violation_time,
                        "violation_ts": row["violation_ts"],
                        "full_image_path": row["full_image_path"],
                        "plate_image_path": row["plate_image_path"],
                        "camera_id": row["camera_id"],
                        "esp32_id": row["esp32_id"],
                        "status": row["status"]
                    })
            
            conn.close()
            
            log.info(f"✅ Exported {len(rows)} violations to: {output_path}")
            return True
        
        except Exception as e:
            log.error(f"Failed to export CSV: {e}")
            return False
    
    def create_sample_csv(self, output_file="sample_violations.csv", allow_test_data: bool = False):
        """Create sample CSV file for reference"""
        if not allow_test_data:
            log.error("Blocked: sample CSV generation is test-only. Use --allow-test-data.")
            return False
        sample_data = [
            {
                "plate_text": "49-E1 999.66",
                "vehicle_type": "CAR",
                "light_state": "RED",
                "violation_time": "2026-03-10 14:35:21",
                "full_image_path": "",
                "plate_image_path": "",
                "camera_id": "CAM_01",
                "plate_confidence": "0.92",
                "speed_kmh": "15.5"
            },
            {
                "plate_text": "29-Y3 036.58",
                "vehicle_type": "MOTORBIKE",
                "light_state": "RED",
                "violation_time": "2026-03-10 14:30:00",
                "full_image_path": "",
                "plate_image_path": "",
                "camera_id": "CAM_01",
                "plate_confidence": "0.88",
                "speed_kmh": "18.2"
            },
            {
                "plate_text": "70-F1 666.66",
                "vehicle_type": "CAR",
                "light_state": "RED",
                "violation_time": "2026-03-10 14:25:00",
                "full_image_path": "",
                "plate_image_path": "",
                "camera_id": "CAM_02",
                "plate_confidence": "0.95",
                "speed_kmh": "12.8"
            },
        ]
        
        try:
            output_path = Path(output_file)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = list(sample_data[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sample_data)
            
            log.info(f"✅ Created sample CSV: {output_path}")
            return True
        
        except Exception as e:
            log.error(f"Failed to create sample CSV: {e}")
            return False

    def get_reference_rows(self):
        """Reference rows for lookup only."""
        rows = []
        if not ALLOW_TEST_DATA:
            return rows
        if SAMPLE_CSV.exists():
            with open(SAMPLE_CSV, "r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    plate_text = row.get("plate_text") or row.get("plate") or ""
                    image_url = row.get("image_path") or self._find_real_image_for_plate(plate_text)
                    rows.append({
                        "plate_text": plate_text,
                        "plate_norm": row.get("plate_norm") or self.normalize_plate(plate_text),
                        "vehicle_type": row.get("vehicle_type", ""),
                        "light_state": row.get("light_state") or row.get("light", ""),
                        "violation_time": row.get("violation_time", ""),
                        "camera_id": row.get("camera_id", ""),
                        "plate_confidence": row.get("plate_confidence") or row.get("confidence") or "0.0",
                        "speed_kmh": row.get("speed_kmh") or row.get("speed") or "0.0",
                        "violation_reason": row.get("violation_reason", ""),
                        "full_image_path": image_url,
                        "plate_image_path": image_url,
                    })
        return rows

# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Import/Export violations from/to CSV"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Import command
    import_parser = subparsers.add_parser("import", help="Import from CSV")
    import_parser.add_argument("csv_file", help="CSV file path")
    import_parser.add_argument("--delimiter", default=",", help="CSV delimiter (default: comma)")
    import_parser.add_argument("--allow-test-data", action="store_true", help="Allow importing sample/test CSV")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export to CSV")
    export_parser.add_argument("--output", default="violations_export.csv", help="Output CSV file")
    export_parser.add_argument("--limit", type=int, help="Limit number of records")
    
    # Sample command
    sample_parser = subparsers.add_parser("sample", help="Create sample CSV")
    sample_parser.add_argument("--allow-test-data", action="store_true", help="Allow generating sample/test CSV")
    
    args = parser.parse_args()
    
    log.info("=" * 70)
    log.info("  CSV IMPORTER/EXPORTER")
    log.info("=" * 70)
    
    importer = CSVImporter()
    
    if args.command == "import":
        allow_test = bool(args.allow_test_data) or ALLOW_TEST_DATA
        if importer.import_from_csv(args.csv_file, args.delimiter, allow_test):
            log.info(f"\n✅ Imported: {importer.imported_count} records")
            if importer.error_count:
                log.warning(f"⚠️  Errors: {importer.error_count} rows")
        else:
            log.error("Import failed")
    
    elif args.command == "export":
        if importer.export_to_csv(args.output, args.limit):
            log.info(f"✅ Export complete")
        else:
            log.error("Export failed")
    
    elif args.command == "sample":
        allow_test = bool(args.allow_test_data) or ALLOW_TEST_DATA
        if importer.create_sample_csv(allow_test_data=allow_test):
            log.info(f"✅ Sample CSV created")
        else:
            log.error("Failed to create sample")
    
    else:
        parser.print_help()
    
    log.info("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\n⛔ Cancelled by user")
    except Exception as e:
        log.error(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
