from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent


def _resolve_database_url() -> str:
    explicit_url = (os.getenv("DATABASE_URL") or "").strip()
    if explicit_url:
        return explicit_url

    raw_path = (os.getenv("DB_PATH") or "traffic_ai.db").strip()
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    db_path = db_path.resolve()

    return f"sqlite:///{db_path.as_posix()}"


DATABASE_URL = _resolve_database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _sqlite_db_path() -> Path | None:
    if not IS_SQLITE:
        return None
    prefix = "sqlite:///"
    raw = DATABASE_URL[len(prefix) :] if DATABASE_URL.startswith(prefix) else ""
    return Path(raw)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_users_schema(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "users"):
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'operator',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")
        return

    columns = _table_columns(conn, "users")
    if "full_name" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        conn.execute(
            "UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''"
        )

    conn.execute(
        """
        UPDATE users
        SET full_name = CASE
            WHEN username = 'admin' THEN 'System Administrator'
            WHEN COALESCE(full_name, '') = '' THEN username
            ELSE full_name
        END
        """
    )
    conn.execute(
        """
        UPDATE users
        SET role = LOWER(COALESCE(role, 'operator'))
        WHERE role IS NOT NULL
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")


def _ensure_violations_schema(conn: sqlite3.Connection) -> None:
    expected_columns = {
        "id",
        "violation_code",
        "camera_id",
        "plate_number",
        "normalized_plate_number",
        "violation_type",
        "violation_time",
        "location_snapshot",
        "full_image_url",
        "vehicle_crop_url",
        "plate_crop_url",
        "stop_line_snapshot_url",
        "light_state",
        "ocr_text_raw",
        "ocr_confidence",
        "vehicle_type",
        "status",
        "created_at",
    }

    if _table_exists(conn, "violations"):
        columns = _table_columns(conn, "violations")
        if not expected_columns.issubset(columns):
            legacy_name = f"violations_legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            conn.execute(f"ALTER TABLE violations RENAME TO {legacy_name}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_code TEXT NOT NULL UNIQUE,
            camera_id INTEGER NOT NULL,
            plate_number TEXT,
            normalized_plate_number TEXT,
            violation_type TEXT NOT NULL,
            violation_time TEXT NOT NULL,
            location_snapshot TEXT,
            full_image_url TEXT,
            vehicle_crop_url TEXT,
            plate_crop_url TEXT,
            stop_line_snapshot_url TEXT,
            light_state TEXT,
            ocr_text_raw TEXT,
            ocr_confidence REAL,
            vehicle_type TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (camera_id) REFERENCES cameras(id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_violations_camera_id ON violations(camera_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_violations_time ON violations(violation_time DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_violations_norm_plate ON violations(normalized_plate_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_violations_status ON violations(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_violations_type ON violations(violation_type)")


def ensure_sqlite_compat_schema() -> None:
    db_path = _sqlite_db_path()
    if not db_path:
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        _ensure_users_schema(conn)
        _ensure_violations_schema(conn)
        conn.commit()
    finally:
        conn.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
