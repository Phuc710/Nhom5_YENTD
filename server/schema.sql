PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ============================================================
-- SMART RED-LIGHT VIOLATION SYSTEM - CORE SCHEMA (SQLite)
-- Tables:
--   1) users
--   2) cameras
--   3) violations
--   4) device_heartbeats
-- ============================================================

-- ------------------------------------------------------------
-- users
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    full_name      TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'operator' CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- ------------------------------------------------------------
-- cameras
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cameras (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_code       TEXT NOT NULL UNIQUE,
    camera_name       TEXT NOT NULL,
    stream_url        TEXT NOT NULL,
    location_name     TEXT NOT NULL,
    latitude          REAL,
    longitude         REAL,
    install_position  TEXT,
    status            TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'degraded', 'maintenance')),
    last_seen         TEXT,
    device_model      TEXT,
    ip_address        TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cameras_status ON cameras(status);
CREATE INDEX IF NOT EXISTS idx_cameras_last_seen ON cameras(last_seen);
CREATE INDEX IF NOT EXISTS idx_cameras_is_active ON cameras(is_active);

-- ------------------------------------------------------------
-- violations
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS violations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    violation_code          TEXT NOT NULL UNIQUE,
    camera_id               INTEGER NOT NULL,
    plate_number            TEXT,
    normalized_plate_number TEXT,
    violation_type          TEXT NOT NULL,
    violation_time          TEXT NOT NULL,
    location_snapshot       TEXT,
    full_image_url          TEXT,
    vehicle_crop_url        TEXT,
    plate_crop_url          TEXT,
    stop_line_snapshot_url  TEXT,
    light_state             TEXT,
    ocr_text_raw            TEXT,
    ocr_confidence          REAL,
    vehicle_type            TEXT,
    status                  TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewing', 'confirmed', 'rejected', 'closed')),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (camera_id) REFERENCES cameras(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_violations_camera_id ON violations(camera_id);
CREATE INDEX IF NOT EXISTS idx_violations_time ON violations(violation_time DESC);
CREATE INDEX IF NOT EXISTS idx_violations_norm_plate ON violations(normalized_plate_number);
CREATE INDEX IF NOT EXISTS idx_violations_status ON violations(status);
CREATE INDEX IF NOT EXISTS idx_violations_type ON violations(violation_type);

-- ------------------------------------------------------------
-- device_heartbeats
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_heartbeats (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id        INTEGER NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('online', 'offline', 'degraded', 'maintenance')),
    latency_ms       INTEGER,
    temperature      REAL,
    signal_strength  INTEGER,
    payload          TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (camera_id) REFERENCES cameras(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_device_heartbeats_camera_time ON device_heartbeats(camera_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_heartbeats_status ON device_heartbeats(status);

-- ------------------------------------------------------------
-- Initial seed data
-- ------------------------------------------------------------
INSERT OR IGNORE INTO users (username, password_hash, full_name, role, is_active)
VALUES
    ('admin', 'scrypt:32768:8:1$8MfhX7dhqPNrVUyL$4f4d1e3b2c9f8a7e5d6c1b4a8f3e2d9c', 'System Administrator', 'admin', 1);

INSERT OR IGNORE INTO cameras (
    camera_code,
    camera_name,
    stream_url,
    location_name,
    latitude,
    longitude,
    install_position,
    status,
    last_seen,
    device_model,
    ip_address,
    is_active
)
VALUES (
    'CAM-HCM-001',
    'Camera Giam Sat #1',
    'rtsp://127.0.0.1/live/cam-1',
    'Nga tu Hang Xanh, TP.HCM',
    10.8037,
    106.7143,
    'Northbound lane / stop-line pole',
    'offline',
    NULL,
    'ESP32-CAM-AI-THINKER',
    '192.168.1.101',
    1
);
