-- =============================================================
-- DATABASE UPDATE SCRIPT (v2)
-- Apply this to an existing v1 database to support new features
-- =============================================================

-- 1. Add AI configuration columns to 'cameras' table
ALTER TABLE cameras 
ADD COLUMN IF NOT EXISTS confidence_threshold DECIMAL(5, 4) DEFAULT 0.5,
ADD COLUMN IF NOT EXISTS operation_mode VARCHAR(50) DEFAULT 'balanced',
ADD COLUMN IF NOT EXISTS rotate_180 BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS flip_horizontal BOOLEAN DEFAULT FALSE;

-- 2. Create 'system_settings' table
CREATE TABLE IF NOT EXISTS system_settings (
    key          VARCHAR(100) PRIMARY KEY,
    value        JSONB NOT NULL,
    description  TEXT,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial system settings if not exists
INSERT INTO system_settings (key, value, description) VALUES
('mqtt_config', '{"host": "thingsboard.cloud", "port": 1883}', 'ThingsBoard MQTT Broker configuration'),
('data_retention', '{"days": 30}', 'Violation record retention policy')
ON CONFLICT (key) DO NOTHING;

-- 3. Update 'view_camera_summary' to include new columns
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
    c.camera_name AS configured_camera_name,
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
    c.stream_url AS configured_stream_url,
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
    COUNT(v.id) AS violations_total,
    c.confidence_threshold, -- NEW
    c.operation_mode,       -- NEW
    c.rotate_180,           -- NEW
    c.flip_horizontal       -- NEW
FROM cameras c
LEFT JOIN camera_provisioning p ON p.camera_id = c.camera_id
LEFT JOIN violations v ON v.camera_id = c.camera_id
GROUP BY
    c.camera_id,
    c.camera_name,
    c.location,
    c.latitude,
    c.longitude,
    c.stream_url,
    c.status,
    c.tb_device_name,
    p.tb_device_name,
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
    c.confidence_threshold,
    c.operation_mode,
    c.rotate_180,
    c.flip_horizontal;

-- 4. Enable RLS for system_settings
ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS public_read_settings ON system_settings;
CREATE POLICY public_read_settings
    ON system_settings FOR SELECT USING (true);

DROP POLICY IF EXISTS service_all_settings ON system_settings;
CREATE POLICY service_all_settings
    ON system_settings FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
