/* ════════════════════════════════════════════════════════════════════════════════
   AI TRAFFIC CONTROL — DATABASE SCHEMA v6.0
   Real-time Violation Detection System — SQLite3
════════════════════════════════════════════════════════════════════════════════ */

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ════════════════════════════════════════════════════════════════
-- USERS TABLE
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'VIEWER',  -- ADMIN, OPERATOR, VIEWER
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ════════════════════════════════════════════════════════════════
-- VIOLATIONS TABLE — Lưu dữ liệu vi phạm thật từ AI detection
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Thông tin biển số (OCR result)
    plate_text TEXT,                      -- Biển số đọc được (ví dụ: "29A-12345")
    plate_confidence REAL DEFAULT 0.0,    -- Độ tin cậy OCR (0-100)
    
    -- Thông tin phương tiện
    vehicle_type TEXT,                    -- MOTORBIKE, CAR, TRUCK, BUS
    vehicle_confidence REAL DEFAULT 0.0,  -- Độ tin cậy detection (0-100)
    
    -- Thông tin vi phạm
    light_state TEXT NOT NULL,            -- RED, YELLOW, GREEN
    speed_kmh REAL DEFAULT 0.0,           -- Tốc độ ước tính
    roi_name TEXT DEFAULT 'STOP_LINE',    -- Vùng phát hiện (STOP_LINE)
    
    -- Thông tin ảnh
    full_image_path TEXT,                 -- Đường dẫn ảnh toàn cảnh (ví dụ: /static/uploads/violations/v_1.jpg)
    plate_image_path TEXT,                -- Đường dẫn ảnh crop biển số (ví dụ: /static/uploads/plates/p_1.jpg)
    
    -- Thông tin thiết bị ghi nhận
    camera_id TEXT DEFAULT 'CAM_01',      -- ID camera (CAM_01, CAM_02, ...)
    esp32_id TEXT DEFAULT 'ESP32_MAIN',   -- ID ESP32
    
    -- Thông tin thời gian
    violation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Thời gian vi phạm
    violation_ts INTEGER,                 -- Unix timestamp
    
    -- Trạng thái record
    status TEXT DEFAULT 'NEW',            -- NEW, REVIEWED, EXPIRED, DELETED
    notes TEXT,                           -- Ghi chú từ quản trị viên
    edited_by INTEGER,                    -- User ID sửa
    edited_at TIMESTAMP,
    
    -- Location info (if available)
    lat REAL,
    lng REAL,
    location_address TEXT
);

CREATE INDEX IF NOT EXISTS idx_violations_ts ON violations(violation_ts DESC);
CREATE INDEX IF NOT EXISTS idx_violations_plate ON violations(plate_text);
CREATE INDEX IF NOT EXISTS idx_violations_light ON violations(light_state);
CREATE INDEX IF NOT EXISTS idx_violations_camera ON violations(camera_id);
CREATE INDEX IF NOT EXISTS idx_violations_status ON violations(status);
CREATE INDEX IF NOT EXISTS idx_violations_vehicle ON violations(vehicle_type);

-- ════════════════════════════════════════════════════════════════
-- DEVICE STATUS TABLE — Theo dõi trạng thái ESP32/Camera
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS device_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    device_id TEXT UNIQUE NOT NULL,       -- ESP32_CAM_01, ESP32_MAIN, LED_7SEG
    device_name TEXT NOT NULL,            -- "ESP32-CAM #1", "ESP32 Main"
    device_type TEXT NOT NULL,            -- CAMERA, ESP32_MAIN, LED_7SEG, LIGHT_CONTROLLER
    
    -- Connection status
    is_online INTEGER DEFAULT 0,          -- 0 = offline, 1 = online
    last_heartbeat TIMESTAMP,             -- Lần cuối nhận heartbeat
    heartbeat_ts INTEGER,                 -- Unix timestamp
    
    -- Hardware info
    ip_address TEXT,                      -- IP của ESP32
    mac_address TEXT,
    firmware_version TEXT,                -- v2.1.3
    
    -- Status metrics
    signal_strength INTEGER DEFAULT 0,    -- WiFi signal (0-100)
    cpu_temp_c REAL DEFAULT 0.0,         -- CPU temperature
    uptime_seconds INTEGER DEFAULT 0,     -- Thời gian hoạt động
    
    -- Statistics
    frames_sent INTEGER DEFAULT 0,        -- Số frame gửi lên
    frames_processed INTEGER DEFAULT 0,   -- Số frame xử lý
    detections_total INTEGER DEFAULT 0,   -- Số detection
    violations_detected INTEGER DEFAULT 0, -- Số vi phạm phát hiện
    
    -- Notes & tracking
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_status_id ON device_status(device_id);
CREATE INDEX IF NOT EXISTS idx_device_status_online ON device_status(is_online);
CREATE INDEX IF NOT EXISTS idx_device_status_type ON device_status(device_type);

-- ════════════════════════════════════════════════════════════════
-- TRAFFIC STATE TABLE — Lịch sử trạng thái đèn giao thông
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS traffic_state_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    light_state TEXT NOT NULL,            -- RED, YELLOW, GREEN
    phase_duration INTEGER NOT NULL,      -- Thời gian pha (giây)
    mode TEXT DEFAULT 'AUTO',             -- AUTO, FORCED_RED, FORCED_GREEN, EMERGENCY
    
    triggered_by TEXT,                    -- SYSTEM, BUTTON, API, EMERGENCY
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_ts INTEGER
);

CREATE INDEX IF NOT EXISTS idx_traffic_state_ts ON traffic_state_history(changed_ts DESC);

-- ════════════════════════════════════════════════════════════════
-- AI CONTEXT TABLE — Lưu trữ context snapshot từ AI engine
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ai_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ts INTEGER,
    
    vehicles_frame INTEGER DEFAULT 0,     -- Số phương tiện/frame
    speed_kmh REAL DEFAULT 0.0,          -- Tốc độ trung bình
    fps REAL DEFAULT 0.0,                -- Frame per second
    
    weather TEXT,                         -- SUN, LIGHT_RAIN, CLOUDY, NIGHT
    light_condition TEXT,                 -- BRIGHT, NORMAL, DARK
    ocr_success_rate REAL DEFAULT 0.0,   -- % thành công
    
    distance_m REAL DEFAULT 5.0,         -- Khoảng cách tối ưu
    roi_coverage INTEGER DEFAULT 100,    -- % vùng được quét
    
    detections_count INTEGER DEFAULT 0,
    violations_count INTEGER DEFAULT 0,
    
    frame_count INTEGER DEFAULT 0,
    dropped_frames INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ai_context_ts ON ai_context(ts DESC);

-- ════════════════════════════════════════════════════════════════
-- AUDIT LOG TABLE — Ghi lại mọi hành động
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    user_id INTEGER,
    action TEXT NOT NULL,                 -- CREATE, UPDATE, DELETE, FORCE_LIGHT, etc.
    resource_type TEXT,                   -- VIOLATION, DEVICE, TRAFFIC_STATE
    resource_id INTEGER,
    
    details TEXT,                         -- JSON details
    ip_address TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(created_at DESC);

-- ════════════════════════════════════════════════════════════════
-- THINGBOARD SYNC TABLE — Theo dõi sync với ThingsBoard
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS thingboard_sync (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    violation_id INTEGER NOT NULL,
    thingboard_id TEXT,                   -- ID returned from ThingsBoard
    
    synced INTEGER DEFAULT 0,             -- 0 = pending, 1 = synced
    sync_timestamp TIMESTAMP,
    
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    
    FOREIGN KEY (violation_id) REFERENCES violations(id)
);

CREATE INDEX IF NOT EXISTS idx_tb_sync_violation ON thingboard_sync(violation_id);
CREATE INDEX IF NOT EXISTS idx_tb_sync_status ON thingboard_sync(synced);

-- ════════════════════════════════════════════════════════════════
-- SYSTEM CONFIGURATION TABLE
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS system_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    config_key TEXT UNIQUE NOT NULL,      -- camera_enable, ocr_enabled, etc.
    config_value TEXT,
    config_type TEXT,                     -- BOOLEAN, INTEGER, FLOAT, STRING, JSON
    
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER
);

CREATE INDEX IF NOT EXISTS idx_config_key ON system_config(config_key);

-- ════════════════════════════════════════════════════════════════
-- INITIALIZE SYSTEM CONFIG
-- ════════════════════════════════════════════════════════════════
INSERT OR IGNORE INTO system_config (config_key, config_value, config_type, description) VALUES
    ('camera_enabled', '1', 'BOOLEAN', 'Enable camera capture'),
    ('ocr_enabled', '1', 'BOOLEAN', 'Enable OCR reading'),
    ('mqtt_enabled', '1', 'BOOLEAN', 'Enable MQTT communication'),
    ('thingboard_enabled', '1', 'BOOLEAN', 'Enable ThingsBoard sync'),
    ('red_light_duration', '30', 'INTEGER', 'Red light phase duration (seconds)'),
    ('yellow_light_duration', '5', 'INTEGER', 'Yellow light phase duration (seconds)'),
    ('green_light_duration', '30', 'INTEGER', 'Green light phase duration (seconds)'),
    ('capture_interval_ms', '500', 'INTEGER', 'Capture interval in milliseconds'),
    ('ocr_confidence_threshold', '0.55', 'FLOAT', 'OCR minimum confidence'),
    ('violation_detection_interval', '3.0', 'FLOAT', 'Violation detection cooldown (seconds)'),
    ('data_retention_days', '30', 'INTEGER', 'Data retention period (days)'),
    ('auto_delete_expired', '1', 'BOOLEAN', 'Auto delete expired records'),
    ('camera_location', '10.8037,106.7143', 'STRING', 'Camera GPS coordinates'),
    ('camera_address', 'Quận Bình Thạnh, TP.HCM', 'STRING', 'Camera location address');

-- ════════════════════════════════════════════════════════════════
-- INITIALIZE DEFAULT ADMIN USER (password: admin)
-- ════════════════════════════════════════════════════════════════
INSERT OR IGNORE INTO users (username, password_hash, email, role, is_active) VALUES
    ('admin', 'scrypt:32768:8:1$8MfhX7dhqPNrVUyL$4f4d1e3b2c9f8a7e5d6c1b4a8f3e2d9c', 'admin@traffic.local', 'ADMIN', 1);