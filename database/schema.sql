-- =============================================================
-- TRAFFIC VIOLATION MONITORING — FINAL SCHEMA
-- Supabase / PostgreSQL — Run once on a fresh project
-- Merged: schema.sql + update_v2.sql + migrate_stream_pipeline.sql
-- UTC storage, frontend renders Asia/Ho_Chi_Minh
-- =============================================================

-- Clean up existing objects
DROP VIEW IF EXISTS view_camera_summary CASCADE;
DROP VIEW IF EXISTS view_daily_stats CASCADE;
DROP VIEW IF EXISTS view_violations_full CASCADE;

DROP TABLE IF EXISTS ocr_results CASCADE;
DROP TABLE IF EXISTS violations CASCADE;
DROP TABLE IF EXISTS detection_zones CASCADE;
DROP TABLE IF EXISTS camera_provisioning CASCADE;
DROP TABLE IF EXISTS cameras CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;

DROP FUNCTION IF EXISTS fn_camera_display_name CASCADE;
DROP FUNCTION IF EXISTS fn_stream_url CASCADE;
DROP FUNCTION IF EXISTS fn_set_updated_at CASCADE;

SET timezone = 'UTC';

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- HELPER FUNCTIONS
-- =============================================================

CREATE OR REPLACE FUNCTION fn_camera_display_name(
    configured_name TEXT,
    configured_tb_device_name TEXT,
    provisioned_device_name TEXT,
    provisioned_project_name TEXT,
    provisioned_tb_device_name TEXT,
    device_code INTEGER
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        NULLIF(BTRIM(configured_name), ''),
        NULLIF(BTRIM(provisioned_device_name), ''),
        NULLIF(BTRIM(provisioned_project_name), ''),
        NULLIF(BTRIM(configured_tb_device_name), ''),
        NULLIF(BTRIM(provisioned_tb_device_name), ''),
        'Camera ' || LPAD(COALESCE(device_code, 0)::TEXT, 3, '0')
    );
$$;

CREATE OR REPLACE FUNCTION fn_stream_url(
    override_url TEXT,
    scheme_name TEXT,
    host_name TEXT,
    port_number INTEGER,
    path_name TEXT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        NULLIF(BTRIM(override_url), ''),
        CASE
            WHEN NULLIF(BTRIM(host_name), '') IS NULL THEN NULL
            ELSE LOWER(COALESCE(NULLIF(BTRIM(scheme_name), ''), 'http'))
                 || '://'
                 || BTRIM(host_name)
                 || CASE
                        WHEN COALESCE(port_number, 0) > 0 THEN ':' || port_number::TEXT
                        ELSE ''
                    END
                 || CASE
                        WHEN LEFT(COALESCE(NULLIF(BTRIM(path_name), ''), '/stream'), 1) = '/'
                            THEN COALESCE(NULLIF(BTRIM(path_name), ''), '/stream')
                        ELSE '/' || COALESCE(NULLIF(BTRIM(path_name), ''), 'stream')
                    END
        END
    );
$$;

CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- =============================================================
-- TABLE: cameras
-- One row = one physical ESP32-S3 camera device
-- =============================================================

CREATE TABLE IF NOT EXISTS cameras (
    id                   SERIAL PRIMARY KEY,
    camera_id            INTEGER UNIQUE NOT NULL,
    camera_name          VARCHAR(100) NOT NULL,
    location             VARCHAR(255) NOT NULL,
    latitude             DECIMAL(10, 7),
    longitude            DECIMAL(10, 7),
    stream_url           VARCHAR(512),
    description          TEXT,
    tb_device_name       VARCHAR(255),
    status               VARCHAR(20) DEFAULT 'inactive'
                         CHECK (status IN ('active', 'inactive', 'error')),
    confidence_threshold DECIMAL(5, 4) DEFAULT 0.5,
    operation_mode       VARCHAR(50)   DEFAULT 'balanced',
    rotate_180           BOOLEAN       DEFAULT FALSE,
    flip_horizontal      BOOLEAN       DEFAULT FALSE,
    created_at           TIMESTAMPTZ   DEFAULT NOW(),
    updated_at           TIMESTAMPTZ   DEFAULT NOW()
);

COMMENT ON TABLE cameras IS 'Static camera registry managed by backend and dashboard';
COMMENT ON COLUMN cameras.stream_url IS 'Optional manual stream URL override. If null, stream URL is built from provisioning data';

-- =============================================================
-- TABLE: camera_provisioning
-- Dynamic identity/runtime info from ESP32-S3 and ThingsBoard
-- =============================================================

CREATE TABLE IF NOT EXISTS camera_provisioning (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id            INTEGER UNIQUE REFERENCES cameras(camera_id) ON DELETE CASCADE,
    tb_device_id         VARCHAR(255),
    tb_device_name       VARCHAR(255),
    device_name          VARCHAR(255),
    project_name         VARCHAR(255),
    device_model         VARCHAR(100),
    wifi_ssid            VARCHAR(255),
    resolution           VARCHAR(50),
    access_token         VARCHAR(255),
    mac_address          VARCHAR(17),
    fw_version           VARCHAR(50),
    idf_version          VARCHAR(50),
    stream_scheme        VARCHAR(10)  DEFAULT 'http',
    stream_host          VARCHAR(255),
    stream_port          INTEGER      DEFAULT 81,
    stream_path          VARCHAR(255) DEFAULT '/stream',
    stream_snapshot_path VARCHAR(255) DEFAULT '/snapshot',
    ip_address           VARCHAR(45),
    last_seen_at         TIMESTAMPTZ,
    last_boot_at         TIMESTAMPTZ,
    online               BOOLEAN      DEFAULT FALSE,
    provisioned_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  DEFAULT NOW(),
    extra_attributes     JSONB        NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE camera_provisioning IS 'Dynamic provisioning and identity info synced from ESP32-S3 and ThingsBoard';
COMMENT ON COLUMN camera_provisioning.extra_attributes IS 'Flexible JSON space for future dynamic fields without changing schema';

-- =============================================================
-- TABLE: detection_zones
-- =============================================================

CREATE TABLE IF NOT EXISTS detection_zones (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id   INTEGER NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
    zone_name   VARCHAR(100) NOT NULL DEFAULT 'zone-1',
    x           INTEGER NOT NULL DEFAULT 0,
    y           INTEGER NOT NULL DEFAULT 0,
    width       INTEGER NOT NULL DEFAULT 100,
    height      INTEGER NOT NULL DEFAULT 100,
    zone_type   VARCHAR(50) DEFAULT 'detection'
                CHECK (zone_type IN ('detection', 'stop_line', 'roi', 'violation_zone')),
    active      BOOLEAN     DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE detection_zones IS 'Detection, stop_line, violation_zone and ROI zones per camera';
COMMENT ON COLUMN detection_zones.zone_type IS 'detection=trong vùng | stop_line=vạch kẻ | violation_zone=vùng sau vạch | roi=roi';

-- =============================================================
-- TABLE: violations
-- =============================================================

CREATE TABLE IF NOT EXISTS violations (
    id                    SERIAL PRIMARY KEY,
    camera_id             INTEGER NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
    license_plate         VARCHAR(20),
    confidence            DECIMAL(5, 4),
    full_image_url        TEXT NOT NULL,
    cropped_vehicle_url   TEXT,
    cropped_plate_url     TEXT,
    stop_line_snapshot_url TEXT,
    violation_type        VARCHAR(50) DEFAULT 'red_light'
                          CHECK (violation_type IN ('red_light', 'wrong_lane', 'speeding')),
    traffic_light_state   VARCHAR(10) DEFAULT 'red'
                          CHECK (traffic_light_state IN ('red', 'yellow', 'green')),
    timestamp             TIMESTAMPTZ NOT NULL,
    vote_count            SMALLINT,
    vote_percent          DECIMAL(5, 2),
    total_frames          SMALLINT,
    track_id              INTEGER,
    image_quality_score   DECIMAL(5, 2),
    bbox_x                INTEGER,
    bbox_y                INTEGER,
    bbox_w                INTEGER,
    bbox_h                INTEGER,
    processed             BOOLEAN DEFAULT TRUE,
    processing_time_ms    INTEGER,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE violations IS 'Traffic violation records with evidence images and processing metadata';
COMMENT ON COLUMN violations.full_image_url          IS 'Main evidence image (snapshot)';
COMMENT ON COLUMN violations.cropped_vehicle_url     IS 'Vehicle crop with padding around plate bbox';
COMMENT ON COLUMN violations.cropped_plate_url       IS 'Direct plate crop for OCR display';
COMMENT ON COLUMN violations.stop_line_snapshot_url  IS 'Full frame at exact moment of stop line crossing';

-- =============================================================
-- TABLE: ocr_results
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

COMMENT ON TABLE ocr_results IS 'Per-frame OCR voting history for debugging and analysis';

-- =============================================================
-- TABLE: system_settings
-- =============================================================

CREATE TABLE IF NOT EXISTS system_settings (
    key          VARCHAR(100) PRIMARY KEY,
    value        JSONB NOT NULL,
    description  TEXT,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE system_settings IS 'Global system-wide configurations';

INSERT INTO system_settings (key, value, description) VALUES
    ('mqtt_config',    '{"host": "thingsboard.cloud", "port": 1883}', 'ThingsBoard MQTT Broker configuration'),
    ('data_retention', '{"days": 30}',                                 'Violation record retention policy')
ON CONFLICT (key) DO NOTHING;

-- =============================================================
-- INDEXES
-- =============================================================

CREATE INDEX IF NOT EXISTS idx_cameras_status    ON cameras(status);
CREATE INDEX IF NOT EXISTS idx_cameras_camera_id ON cameras(camera_id);
CREATE INDEX IF NOT EXISTS idx_cameras_tb_name   ON cameras(tb_device_name);

CREATE INDEX IF NOT EXISTS idx_prov_camera_id    ON camera_provisioning(camera_id);
CREATE INDEX IF NOT EXISTS idx_prov_mac          ON camera_provisioning(mac_address);
CREATE INDEX IF NOT EXISTS idx_prov_tb_name      ON camera_provisioning(tb_device_name);
CREATE INDEX IF NOT EXISTS idx_prov_online_seen  ON camera_provisioning(online, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_zones_camera_id   ON detection_zones(camera_id);
CREATE INDEX IF NOT EXISTS idx_zones_active      ON detection_zones(camera_id, active);

CREATE INDEX IF NOT EXISTS idx_viol_camera_id    ON violations(camera_id);
CREATE INDEX IF NOT EXISTS idx_viol_timestamp    ON violations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_viol_plate        ON violations(license_plate);
CREATE INDEX IF NOT EXISTS idx_viol_created      ON violations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_viol_track        ON violations(track_id);
CREATE INDEX IF NOT EXISTS idx_viol_cam_ts       ON violations(camera_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ocr_violation_id  ON ocr_results(violation_id);
CREATE INDEX IF NOT EXISTS idx_ocr_track_id      ON ocr_results(track_id);

-- =============================================================
-- TRIGGERS
-- =============================================================

DROP TRIGGER IF EXISTS trg_cameras_updated_at ON cameras;
CREATE TRIGGER trg_cameras_updated_at
    BEFORE UPDATE ON cameras
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_prov_updated_at ON camera_provisioning;
CREATE TRIGGER trg_prov_updated_at
    BEFORE UPDATE ON camera_provisioning
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_zones_updated_at ON detection_zones;
CREATE TRIGGER trg_zones_updated_at
    BEFORE UPDATE ON detection_zones
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_violations_updated_at ON violations;
CREATE TRIGGER trg_violations_updated_at
    BEFORE UPDATE ON violations
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- =============================================================
-- VIEWS
-- =============================================================

CREATE OR REPLACE VIEW view_violations_full
WITH (security_invoker = true)
AS
SELECT
    v.id,
    v.license_plate,
    v.confidence,
    v.full_image_url,
    v.cropped_vehicle_url,
    v.cropped_plate_url,
    v.stop_line_snapshot_url,
    v.violation_type,
    v.traffic_light_state,
    v.timestamp,
    v.timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh' AS timestamp_vn,
    v.vote_count,
    v.vote_percent,
    v.total_frames,
    v.track_id,
    v.image_quality_score,
    v.bbox_x,
    v.bbox_y,
    v.bbox_w,
    v.bbox_h,
    v.processing_time_ms,
    v.created_at,
    c.camera_id,
    fn_camera_display_name(
        c.camera_name,
        c.tb_device_name,
        p.device_name,
        p.project_name,
        p.tb_device_name,
        c.camera_id
    ) AS camera_name,
    c.location,
    c.latitude,
    c.longitude,
    fn_stream_url(
        c.stream_url,
        p.stream_scheme,
        COALESCE(p.stream_host, p.ip_address),
        p.stream_port,
        p.stream_path
    ) AS stream_url,
    COALESCE(c.tb_device_name, p.tb_device_name) AS tb_device_name,
    p.device_name,
    p.project_name,
    p.device_model,
    p.resolution,
    p.ip_address,
    p.fw_version,
    p.last_seen_at
FROM violations v
JOIN cameras c ON v.camera_id = c.camera_id
LEFT JOIN camera_provisioning p ON p.camera_id = c.camera_id;

CREATE OR REPLACE VIEW view_daily_stats
WITH (security_invoker = true)
AS
SELECT
    (timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE AS date_vn,
    camera_id,
    COUNT(*)                                           AS violation_count,
    COUNT(DISTINCT license_plate)                      AS unique_plates,
    ROUND(AVG(confidence)::NUMERIC, 4)                 AS avg_confidence,
    ROUND(AVG(image_quality_score)::NUMERIC, 2)        AS avg_quality
FROM violations
GROUP BY date_vn, camera_id
ORDER BY date_vn DESC;

CREATE OR REPLACE VIEW view_camera_summary
WITH (security_invoker = true)
AS
SELECT
    c.camera_id,
    fn_camera_display_name(
        c.camera_name,
        c.tb_device_name,
        p.device_name,
        p.project_name,
        p.tb_device_name,
        c.camera_id
    ) AS camera_name,
    c.camera_name   AS configured_camera_name,
    c.location,
    c.latitude,
    c.longitude,
    fn_stream_url(
        c.stream_url,
        p.stream_scheme,
        COALESCE(p.stream_host, p.ip_address),
        p.stream_port,
        p.stream_path
    ) AS stream_url,
    c.stream_url    AS configured_stream_url,
    c.status,
    COALESCE(c.tb_device_name, p.tb_device_name) AS tb_device_name,
    p.device_name,
    p.project_name,
    p.device_model,
    p.wifi_ssid,
    p.resolution,
    p.stream_scheme,
    p.stream_host,
    p.stream_port,
    p.stream_path,
    p.stream_snapshot_path,
    p.ip_address,
    p.fw_version,
    p.mac_address,
    p.last_seen_at,
    p.last_boot_at,
    p.online,
    COUNT(v.id) FILTER (
        WHERE (v.timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
              = (NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
    ) AS violations_today,
    COUNT(v.id)     AS violations_total,
    c.confidence_threshold,
    c.operation_mode,
    c.rotate_180,
    c.flip_horizontal
FROM cameras c
LEFT JOIN camera_provisioning p ON p.camera_id = c.camera_id
LEFT JOIN violations v          ON v.camera_id = c.camera_id
GROUP BY
    c.camera_id, c.camera_name, c.location, c.latitude, c.longitude,
    c.stream_url, c.status, c.tb_device_name,
    p.tb_device_name, p.device_name, p.project_name, p.device_model,
    p.wifi_ssid, p.resolution, p.stream_scheme, p.stream_host,
    p.stream_port, p.stream_path, p.stream_snapshot_path,
    p.ip_address, p.fw_version, p.mac_address, p.last_seen_at,
    p.last_boot_at, p.online,
    c.confidence_threshold, c.operation_mode, c.rotate_180, c.flip_horizontal;

-- =============================================================
-- ROW LEVEL SECURITY
-- =============================================================

ALTER TABLE cameras           ENABLE ROW LEVEL SECURITY;
ALTER TABLE camera_provisioning ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection_zones   ENABLE ROW LEVEL SECURITY;
ALTER TABLE violations        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_results       ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_settings   ENABLE ROW LEVEL SECURITY;

-- Public read
DROP POLICY IF EXISTS public_read_cameras       ON cameras;
CREATE POLICY public_read_cameras       ON cameras           FOR SELECT USING (true);

DROP POLICY IF EXISTS public_read_violations    ON violations;
CREATE POLICY public_read_violations    ON violations         FOR SELECT USING (true);

DROP POLICY IF EXISTS public_read_zones         ON detection_zones;
CREATE POLICY public_read_zones         ON detection_zones    FOR SELECT USING (true);

DROP POLICY IF EXISTS public_read_provisioning  ON camera_provisioning;
CREATE POLICY public_read_provisioning  ON camera_provisioning FOR SELECT USING (true);

DROP POLICY IF EXISTS public_read_settings      ON system_settings;
CREATE POLICY public_read_settings      ON system_settings    FOR SELECT USING (true);

-- Service role write
DROP POLICY IF EXISTS service_insert_cameras    ON cameras;
CREATE POLICY service_insert_cameras    ON cameras FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_update_cameras    ON cameras;
CREATE POLICY service_update_cameras    ON cameras FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_insert_violations ON violations;
CREATE POLICY service_insert_violations ON violations FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_update_violations ON violations;
CREATE POLICY service_update_violations ON violations FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_all_provisioning  ON camera_provisioning;
CREATE POLICY service_all_provisioning  ON camera_provisioning FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_all_zones         ON detection_zones;
CREATE POLICY service_all_zones         ON detection_zones FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_insert_ocr        ON ocr_results;
CREATE POLICY service_insert_ocr        ON ocr_results FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS service_all_settings      ON system_settings;
CREATE POLICY service_all_settings      ON system_settings FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
