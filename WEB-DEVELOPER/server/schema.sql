PRAGMA foreign_keys = ON;

-- ======================================
-- USERS
-- ======================================

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'ADMIN',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_username
ON users(username);

-- ======================================
-- VIOLATIONS
-- ======================================

CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate TEXT NOT NULL,
    light TEXT NOT NULL,
    speed_kmh REAL,
    roi TEXT NOT NULL,
    image_url TEXT,
    ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_violations_ts
ON violations(ts DESC);

CREATE INDEX IF NOT EXISTS idx_violations_plate
ON violations(plate);

CREATE INDEX IF NOT EXISTS idx_violations_light
ON violations(light);

-- ======================================
-- DEVICE STATUS
-- ======================================

CREATE TABLE IF NOT EXISTS device_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    online INTEGER NOT NULL,
    ip TEXT,
    last_seen INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_device_status_device
ON device_status(device_id);
