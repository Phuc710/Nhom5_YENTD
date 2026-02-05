PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'ADMIN',
  created_at INTEGER NOT NULL
);

CREATE TABLE violations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plate TEXT NOT NULL,
  vehicle_type TEXT NOT NULL,
  speed_kmh REAL,
  light TEXT NOT NULL,
  roi TEXT NOT NULL,
  image_url TEXT,
  ts INTEGER NOT NULL,
  note TEXT
);

CREATE INDEX idx_violations_ts ON violations(ts DESC);
CREATE INDEX idx_violations_plate ON violations(plate);
CREATE INDEX idx_violations_light ON violations(light);

CREATE TABLE device_status (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  online INTEGER NOT NULL,
  ip TEXT,
  note TEXT,
  last_seen INTEGER NOT NULL
);

INSERT INTO users(username,password_hash,role,created_at)
VALUES (
  'Admin',
  'pbkdf2:sha256:260000$ENTERPRISE$XW7sO9K2Q0uKp6s9cXxP3mJ3b0Qy',
  'ADMIN',
  strftime('%s','now')
);
