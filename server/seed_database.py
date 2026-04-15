"""
Seed data for the new core schema:
- users
- cameras
- violations
- device_heartbeats

This script does NOT delete the existing traffic_ai.db.
It only inserts sample rows into the current database.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "traffic_ai.db"
UPLOADS_DIR = Path(__file__).parent.parent / "imge"


SAMPLE_CAMERAS = [
    {
        "camera_code": "CAM-HCM-001",
        "camera_name": "Camera Giam Sat #1",
        "stream_url": "rtsp://127.0.0.1/live/cam-1",
        "location_name": "Nga tu Hang Xanh, TP.HCM",
        "latitude": 10.8037,
        "longitude": 106.7143,
        "install_position": "Northbound lane / stop-line pole",
        "status": "online",
        "device_model": "ESP32-CAM-AI-THINKER",
        "ip_address": "192.168.1.101",
        "is_active": 1,
    },
    {
        "camera_code": "CAM-HCM-002",
        "camera_name": "Camera Giam Sat #2",
        "stream_url": "rtsp://127.0.0.1/live/cam-2",
        "location_name": "Dien Bien Phu - Dinh Bo Linh",
        "latitude": 10.8012,
        "longitude": 106.7104,
        "install_position": "Eastbound lane / mast-arm",
        "status": "online",
        "device_model": "ESP32-CAM-AI-THINKER",
        "ip_address": "192.168.1.102",
        "is_active": 1,
    },
]

SAMPLE_VIOLATIONS = [
    {
        "violation_code": "VIO-2026-0001",
        "camera_code": "CAM-HCM-001",
        "plate_number": "49-E1 999.66",
        "normalized_plate_number": "49E199966",
        "violation_type": "red_light_crossing",
        "light_state": "RED",
        "ocr_text_raw": "49E199966",
        "ocr_confidence": 0.98,
        "vehicle_type": "motorbike",
        "status": "new",
    },
    {
        "violation_code": "VIO-2026-0002",
        "camera_code": "CAM-HCM-002",
        "plate_number": "70-F1 666.66",
        "normalized_plate_number": "70F166666",
        "violation_type": "red_light_crossing",
        "light_state": "RED",
        "ocr_text_raw": "70F166666",
        "ocr_confidence": 0.94,
        "vehicle_type": "car",
        "status": "confirmed",
    },
]

SAMPLE_HEARTBEATS = [
    {"camera_code": "CAM-HCM-001", "status": "online", "latency_ms": 42, "temperature": 46.2, "signal_strength": 83},
    {"camera_code": "CAM-HCM-002", "status": "online", "latency_ms": 58, "temperature": 47.8, "signal_strength": 79},
]


def _canon_plate(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def find_real_image_for_plate(plate: str) -> str:
    canon = _canon_plate(plate)
    for p in UPLOADS_DIR.glob("*.*"):
        if not p.is_file() or p.name.lower() == "admin.jpg":
            continue
        if _canon_plate(p.stem) == canon:
            return f"/imge/{p.name}"
    return ""


def _require_tables(conn: sqlite3.Connection) -> None:
    needed = {"users", "cameras", "violations", "device_heartbeats"}
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cur.fetchall()}
    missing = sorted(needed - existing)
    if missing:
        raise RuntimeError(
            "Missing required tables: "
            + ", ".join(missing)
            + ". Recreate DB from schema.sql first."
        )


def _camera_id_by_code(conn: sqlite3.Connection, camera_code: str) -> int | None:
    cur = conn.cursor()
    cur.execute("SELECT id FROM cameras WHERE camera_code = ?", (camera_code,))
    row = cur.fetchone()
    return int(row[0]) if row else None


def seed_users(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash, full_name, role, is_active)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "operator",
            "scrypt:32768:8:1$sample$samplehash",
            "Traffic Operator",
            "operator",
            1,
        ),
    )
    conn.commit()
    print("Seeded users")


def seed_cameras(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    for cam in SAMPLE_CAMERAS:
        cur.execute(
            """
            INSERT INTO cameras (
                camera_code, camera_name, stream_url, location_name,
                latitude, longitude, install_position, status, last_seen,
                device_model, ip_address, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(camera_code) DO UPDATE SET
                camera_name=excluded.camera_name,
                stream_url=excluded.stream_url,
                location_name=excluded.location_name,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                install_position=excluded.install_position,
                status=excluded.status,
                last_seen=excluded.last_seen,
                device_model=excluded.device_model,
                ip_address=excluded.ip_address,
                is_active=excluded.is_active,
                updated_at=excluded.updated_at
            """,
            (
                cam["camera_code"],
                cam["camera_name"],
                cam["stream_url"],
                cam["location_name"],
                cam["latitude"],
                cam["longitude"],
                cam["install_position"],
                cam["status"],
                now,
                cam["device_model"],
                cam["ip_address"],
                cam["is_active"],
                now,
                now,
            ),
        )
    conn.commit()
    print(f"Seeded cameras: {len(SAMPLE_CAMERAS)}")


def seed_violations(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    now = datetime.now()
    for i, vio in enumerate(SAMPLE_VIOLATIONS, 1):
        cam_id = _camera_id_by_code(conn, vio["camera_code"])
        if cam_id is None:
            print(f"Skip violation {vio['violation_code']}: camera not found")
            continue

        vtime = (now - timedelta(minutes=i * 5)).isoformat(timespec="seconds")
        full_image = find_real_image_for_plate(vio["plate_number"])
        stop_line = full_image
        plate_crop = full_image
        vehicle_crop = full_image

        cur.execute(
            """
            INSERT INTO violations (
                violation_code, camera_id, plate_number, normalized_plate_number,
                violation_type, violation_time, location_snapshot,
                full_image_url, vehicle_crop_url, plate_crop_url, stop_line_snapshot_url,
                light_state, ocr_text_raw, ocr_confidence, vehicle_type, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(violation_code) DO UPDATE SET
                camera_id=excluded.camera_id,
                plate_number=excluded.plate_number,
                normalized_plate_number=excluded.normalized_plate_number,
                violation_type=excluded.violation_type,
                violation_time=excluded.violation_time,
                location_snapshot=excluded.location_snapshot,
                full_image_url=excluded.full_image_url,
                vehicle_crop_url=excluded.vehicle_crop_url,
                plate_crop_url=excluded.plate_crop_url,
                stop_line_snapshot_url=excluded.stop_line_snapshot_url,
                light_state=excluded.light_state,
                ocr_text_raw=excluded.ocr_text_raw,
                ocr_confidence=excluded.ocr_confidence,
                vehicle_type=excluded.vehicle_type,
                status=excluded.status
            """,
            (
                vio["violation_code"],
                cam_id,
                vio["plate_number"],
                vio["normalized_plate_number"],
                vio["violation_type"],
                vtime,
                "STOP_LINE",
                full_image,
                vehicle_crop,
                plate_crop,
                stop_line,
                vio["light_state"],
                vio["ocr_text_raw"],
                vio["ocr_confidence"],
                vio["vehicle_type"],
                vio["status"],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    conn.commit()
    print(f"Seeded violations: {len(SAMPLE_VIOLATIONS)}")


def seed_device_heartbeats(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for hb in SAMPLE_HEARTBEATS:
        cam_id = _camera_id_by_code(conn, hb["camera_code"])
        if cam_id is None:
            continue

        payload = (
            '{"source":"seed_database.py","camera_code":"'
            + hb["camera_code"]
            + '","note":"sample heartbeat"}'
        )
        cur.execute(
            """
            INSERT INTO device_heartbeats (
                camera_id, status, latency_ms, temperature, signal_strength, payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cam_id,
                hb["status"],
                hb["latency_ms"],
                hb["temperature"],
                hb["signal_strength"],
                payload,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        cur.execute(
            "UPDATE cameras SET status = ?, last_seen = ?, updated_at = ? WHERE id = ?",
            (
                hb["status"],
                datetime.now().isoformat(timespec="seconds"),
                datetime.now().isoformat(timespec="seconds"),
                cam_id,
            ),
        )
    conn.commit()
    print(f"Seeded device_heartbeats: {len(SAMPLE_HEARTBEATS)}")


def verify_data(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    print("\nData verification")

    cur.execute("SELECT COUNT(*) FROM users")
    print(f"Users: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM cameras")
    print(f"Cameras: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM violations")
    print(f"Violations: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM device_heartbeats")
    print(f"Device heartbeats: {cur.fetchone()[0]}")


def main() -> int:
    print("=" * 70)
    print("SEED DATABASE - NEW CORE SCHEMA")
    print("=" * 70)

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run: sqlite3 traffic_ai.db < schema.sql")
        return 1

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA foreign_keys = ON")

        _require_tables(conn)
        seed_users(conn)
        seed_cameras(conn)
        seed_violations(conn)
        seed_device_heartbeats(conn)
        verify_data(conn)

        conn.close()
        print("\nSeeding complete")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
