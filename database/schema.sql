-- =============================================================
-- HỆ THỐNG PHÁT HIỆN VI PHẠM GIAO THÔNG
-- Supabase (PostgreSQL) — Production Schema
-- Múi giờ: UTC, hiển thị +07:00 ở frontend
-- Không có sample data — chỉ schema thuần.
-- =============================================================

SET timezone = 'UTC';

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- TABLE: cameras
-- Một bản ghi = một thiết bị ESP32-S3-CAM vật lý
-- =============================================================
CREATE TABLE IF NOT EXISTS cameras (
    id              SERIAL PRIMARY KEY,
    camera_id       INTEGER UNIQUE NOT NULL,       -- ID số của camera (1, 2, 3...)
    camera_name     VARCHAR(100) NOT NULL,          -- Tên hiển thị
    location        VARCHAR(255) NOT NULL,          -- Mô tả vị trí (ngắn gọn)
    latitude        DECIMAL(10, 7),                -- Tọa độ GPS
    longitude       DECIMAL(10, 7),
    stream_url      VARCHAR(512),                  -- URL stream ESP32 (http://ip/stream)
    description     TEXT,                          -- Ghi chú thêm
    tb_device_name  VARCHAR(255),                  -- Tên thiết bị trên ThingsBoard
    status          VARCHAR(20) DEFAULT 'inactive' -- active | inactive | error
                    CHECK (status IN ('active','inactive','error')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE cameras IS 'Thiết bị camera ESP32-S3-CAM — trạng thái đồng bộ với ThingsBoard';
COMMENT ON COLUMN cameras.stream_url IS 'HTTP MJPEG stream từ ESP32, ví dụ http://192.168.1.100/stream';

-- =============================================================
-- TABLE: camera_provisioning
-- Lưu thông tin provisioning tự động: MAC, token, IP, firmware
-- Được cập nhật mỗi khi ESP32 boot và provision thành công
-- =============================================================
CREATE TABLE IF NOT EXISTS camera_provisioning (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id       INTEGER UNIQUE REFERENCES cameras(camera_id) ON DELETE CASCADE,
    tb_device_id    VARCHAR(255),                  -- ID thiết bị trên ThingsBoard
    access_token    VARCHAR(255),                  -- Token MQTT của thiết bị
    mac_address     VARCHAR(17),                   -- MAC WiFi (AA:BB:CC:DD:EE:FF)
    fw_version      VARCHAR(50),                   -- Phiên bản firmware
    idf_version     VARCHAR(50),                   -- ESP-IDF version
    ip_address      VARCHAR(45),                   -- IP local
    last_seen_at    TIMESTAMPTZ,                   -- Lần cuối thiết bị online
    online          BOOLEAN DEFAULT FALSE,
    provisioned_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE camera_provisioning IS 'Thông tin provisioning ESP32: MAC, token, firmware — sync từ ThingsBoard';

-- =============================================================
-- TABLE: detection_zones
-- Vùng phát hiện vi phạm vẽ trên camera (JSON box)
-- Lưu theo tọa độ tương đối (0..1) so với kích thước ảnh
-- =============================================================
CREATE TABLE IF NOT EXISTS detection_zones (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id   INTEGER NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
    zone_name   VARCHAR(100) NOT NULL DEFAULT 'zone-1',
    -- Tọa độ pixel tuyệt đối (frontend chuẩn hóa về theo resolution camera)
    x           INTEGER NOT NULL DEFAULT 0,
    y           INTEGER NOT NULL DEFAULT 0,
    width       INTEGER NOT NULL DEFAULT 100,
    height      INTEGER NOT NULL DEFAULT 100,
    zone_type   VARCHAR(50) DEFAULT 'detection'   -- detection | stop_line | roi
                CHECK (zone_type IN ('detection','stop_line','roi')),
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE detection_zones IS 'Zones vẽ trên camera để giới hạn vùng detect vi phạm';

-- =============================================================
-- TABLE: violations
-- Bản ghi vi phạm: 1 xe vượt đèn đỏ = 1 record
-- =============================================================
CREATE TABLE IF NOT EXISTS violations (
    id                  SERIAL PRIMARY KEY,
    camera_id           INTEGER NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,

    -- Biển số xe
    license_plate       VARCHAR(20),               -- BSX phát hiện được
    confidence          DECIMAL(5, 4),             -- Độ tin cậy OCR (0.0 - 1.0)

    -- 2 ảnh bắt buộc
    full_image_url      TEXT NOT NULL,             -- Ảnh full frame (xe + đèn)
    cropped_plate_url   TEXT,                      -- Ảnh crop biển số

    -- Chi tiết vi phạm
    violation_type      VARCHAR(50) DEFAULT 'red_light'
                        CHECK (violation_type IN ('red_light','wrong_lane','speeding')),
    traffic_light_state VARCHAR(10) DEFAULT 'red'
                        CHECK (traffic_light_state IN ('red','yellow','green')),
    timestamp           TIMESTAMPTZ NOT NULL,      -- Thời điểm vi phạm chính xác

    -- Dữ liệu xử lý multi-frame (voting)
    vote_count          SMALLINT,                  -- Số frame bỏ phiếu BSX này
    vote_percent        DECIMAL(5, 2),             -- % bỏ phiếu (0..100)
    total_frames        SMALLINT,                  -- Tổng frame xử lý
    track_id            INTEGER,                   -- ID tracking xe

    -- Chất lượng ảnh
    image_quality_score DECIMAL(5, 2),             -- Score 0..100

    -- Bounding box vị trí xe trên ảnh full (pixel)
    bbox_x              INTEGER,
    bbox_y              INTEGER,
    bbox_w              INTEGER,
    bbox_h              INTEGER,

    -- Trạng thái xử lý
    processed           BOOLEAN DEFAULT TRUE,
    processing_time_ms  INTEGER,

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE violations IS 'Vi phạm giao thông — full_image + cropped_plate + BSX + thời gian';

-- =============================================================
-- TABLE: ocr_results
-- Chi tiết voting OCR từng frame (debug / phân tích)
-- =============================================================
CREATE TABLE IF NOT EXISTS ocr_results (
    id              SERIAL PRIMARY KEY,
    violation_id    INTEGER REFERENCES violations(id) ON DELETE CASCADE,
    frame_id        INTEGER NOT NULL,
    track_id        INTEGER,
    license_plate   VARCHAR(20),
    confidence      DECIMAL(5, 4),
    quality_score   DECIMAL(5, 2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ocr_results IS 'Lịch sử voting OCR từng frame — để debug độ chính xác nhận biết BSX';

-- =============================================================
-- INDEXES — tối ưu query thường dùng
-- =============================================================

-- cameras
CREATE INDEX IF NOT EXISTS idx_cameras_status      ON cameras(status);
CREATE INDEX IF NOT EXISTS idx_cameras_camera_id   ON cameras(camera_id);

-- camera_provisioning
CREATE INDEX IF NOT EXISTS idx_prov_camera_id      ON camera_provisioning(camera_id);
CREATE INDEX IF NOT EXISTS idx_prov_mac            ON camera_provisioning(mac_address);

-- detection_zones
CREATE INDEX IF NOT EXISTS idx_zones_camera_id     ON detection_zones(camera_id);
CREATE INDEX IF NOT EXISTS idx_zones_active        ON detection_zones(camera_id, active);

-- violations (critical for performance)
CREATE INDEX IF NOT EXISTS idx_viol_camera_id      ON violations(camera_id);
CREATE INDEX IF NOT EXISTS idx_viol_timestamp      ON violations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_viol_plate          ON violations(license_plate);
CREATE INDEX IF NOT EXISTS idx_viol_created        ON violations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_viol_track          ON violations(track_id);
CREATE INDEX IF NOT EXISTS idx_viol_cam_ts         ON violations(camera_id, timestamp DESC);

-- ocr_results
CREATE INDEX IF NOT EXISTS idx_ocr_violation_id    ON ocr_results(violation_id);
CREATE INDEX IF NOT EXISTS idx_ocr_track_id        ON ocr_results(track_id);

-- =============================================================
-- TRIGGERS — auto-update updated_at
-- =============================================================

CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_cameras_updated_at
    BEFORE UPDATE ON cameras
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_prov_updated_at
    BEFORE UPDATE ON camera_provisioning
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_zones_updated_at
    BEFORE UPDATE ON detection_zones
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_violations_updated_at
    BEFORE UPDATE ON violations
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- =============================================================
-- VIEWS — dùng cho dashboard
-- =============================================================

-- Vi phạm kèm thông tin camera (cho web)
CREATE OR REPLACE VIEW view_violations_full
WITH (security_invoker = true)
AS
SELECT
    v.id,
    v.license_plate,
    v.confidence,
    v.full_image_url,
    v.cropped_plate_url,
    v.violation_type,
    v.traffic_light_state,
    v.timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh' AS timestamp_vn,
    v.vote_count,
    v.vote_percent,
    v.image_quality_score,
    v.bbox_x, v.bbox_y, v.bbox_w, v.bbox_h,
    v.created_at,
    c.camera_id,
    c.camera_name,
    c.location,
    c.latitude,
    c.longitude,
    c.stream_url,
    p.ip_address,
    p.fw_version,
    p.last_seen_at
FROM violations v
JOIN cameras c ON v.camera_id = c.camera_id
LEFT JOIN camera_provisioning p ON p.camera_id = c.camera_id;

-- Dashboard stats theo ngày (UTC+7)
CREATE OR REPLACE VIEW view_daily_stats
WITH (security_invoker = true)
AS
SELECT
    (timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE AS date_vn,
    camera_id,
    COUNT(*)                        AS violation_count,
    COUNT(DISTINCT license_plate)   AS unique_plates,
    ROUND(AVG(confidence)::NUMERIC, 4) AS avg_confidence,
    ROUND(AVG(image_quality_score)::NUMERIC, 2) AS avg_quality
FROM violations
GROUP BY date_vn, camera_id
ORDER BY date_vn DESC;

-- Camera summary cho dashboard card
CREATE OR REPLACE VIEW view_camera_summary
WITH (security_invoker = true)
AS
SELECT
    c.camera_id,
    c.camera_name,
    c.location,
    c.latitude,
    c.longitude,
    c.stream_url,
    c.status,
    c.tb_device_name,
    p.ip_address,
    p.fw_version,
    p.mac_address,
    p.last_seen_at,
    p.online,
    COUNT(v.id) FILTER (
        WHERE (v.timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
              = (NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
    ) AS violations_today,
    COUNT(v.id) AS violations_total
FROM cameras c
LEFT JOIN camera_provisioning p ON p.camera_id = c.camera_id
LEFT JOIN violations v ON v.camera_id = c.camera_id
GROUP BY c.camera_id, c.camera_name, c.location, c.latitude, c.longitude,
         c.stream_url, c.status, c.tb_device_name,
         p.ip_address, p.fw_version, p.mac_address, p.last_seen_at, p.online;

-- =============================================================
-- ROW LEVEL SECURITY (Supabase RLS)
-- =============================================================

ALTER TABLE cameras              ENABLE ROW LEVEL SECURITY;
ALTER TABLE camera_provisioning  ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection_zones      ENABLE ROW LEVEL SECURITY;
ALTER TABLE violations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_results          ENABLE ROW LEVEL SECURITY;

-- Public read (dashboard không yêu cầu đăng nhập)
CREATE POLICY "public_read_cameras"
    ON cameras FOR SELECT USING (true);

CREATE POLICY "public_read_violations"
    ON violations FOR SELECT USING (true);

CREATE POLICY "public_read_zones"
    ON detection_zones FOR SELECT USING (true);

CREATE POLICY "public_read_provisioning"
    ON camera_provisioning FOR SELECT USING (true);

-- Backend (service_role) được phép INSERT/UPDATE/DELETE
CREATE POLICY "service_insert_cameras"
    ON cameras FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_update_cameras"
    ON cameras FOR UPDATE USING (auth.role() = 'service_role');

CREATE POLICY "service_insert_violations"
    ON violations FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_update_violations"
    ON violations FOR UPDATE USING (auth.role() = 'service_role');

CREATE POLICY "service_all_provisioning"
    ON camera_provisioning FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_all_zones"
    ON detection_zones FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "service_insert_ocr"
    ON ocr_results FOR INSERT WITH CHECK (auth.role() = 'service_role');
