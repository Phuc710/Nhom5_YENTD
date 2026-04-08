-- =============================================================
-- SEED DATA — Sample data for testing
-- Run after schema.sql
-- =============================================================

-- Sample cameras
INSERT INTO cameras (camera_id, camera_name, location, latitude, longitude, status, description)
VALUES
    (1, 'Cam Ngã Tư Thủ Đức',   'Ngã tư Thủ Đức, TP.HCM',     10.8483740, 106.7558380, 'active',   'Camera giám sát ngã tư chính'),
    (2, 'Cam Đường Phạm Văn Đồng', 'Đường Phạm Văn Đồng, TP.HCM', 10.8389150, 106.6884820, 'active',   'Camera giám sát lưu lượng'),
    (3, 'Cam Cầu Sài Gòn',      'Cầu Sài Gòn, TP.HCM',         10.8002480, 106.7268750, 'inactive', 'Camera giám sát cầu')
ON CONFLICT (camera_id) DO NOTHING;

-- Sample provisioning for camera 1 (ESP32-S3)
INSERT INTO camera_provisioning (camera_id, device_name, project_name, device_model, wifi_ssid, resolution, stream_host, stream_port, stream_path, ip_address, mac_address, fw_version, online)
VALUES
    (1, 'ESP32-CAM-001', 'TrafficCam-ThuDuc', 'ESP32-S3-WROOM', 'TrafficNet-5G', '640x480', '192.168.1.101', 81, '/stream', '192.168.1.101', 'AA:BB:CC:DD:EE:01', 'v1.2.0', true),
    (2, 'ESP32-CAM-002', 'TrafficCam-PVD',    'ESP32-S3-WROOM', 'TrafficNet-5G', '640x480', '192.168.1.102', 81, '/stream', '192.168.1.102', 'AA:BB:CC:DD:EE:02', 'v1.2.0', true)
ON CONFLICT (camera_id) DO NOTHING;

-- Sample detection zones
INSERT INTO detection_zones (camera_id, zone_name, x, y, width, height, zone_type, active)
VALUES
    (1, 'detection-zone-1',  100, 200, 400, 300, 'detection',      true),
    (1, 'stop-line-1',       50,  450, 540, 10,  'stop_line',      true),
    (1, 'violation-zone-1',  50,  460, 540, 200, 'violation_zone', true),
    (2, 'detection-zone-1',  80,  150, 480, 350, 'detection',      true);

-- Sample violations
INSERT INTO violations (camera_id, license_plate, confidence, full_image_url, violation_type, traffic_light_state, timestamp, vote_count, vote_percent, total_frames, track_id, processing_time_ms)
VALUES
    (1, '51F-123.45', 0.9520, '/storage/violations/v001_full.jpg', 'red_light', 'red',    NOW() - INTERVAL '2 hours',  8, 88.89, 9, 42, 156),
    (1, '59C-678.90', 0.8870, '/storage/violations/v002_full.jpg', 'red_light', 'red',    NOW() - INTERVAL '1 hour',   6, 75.00, 8, 55, 203),
    (2, '51G-111.22', 0.9310, '/storage/violations/v003_full.jpg', 'wrong_lane', 'green', NOW() - INTERVAL '30 minutes', 10, 90.91, 11, 18, 178);

-- Sample OCR results (voting frames for violation 1)
INSERT INTO ocr_results (violation_id, frame_id, track_id, license_plate, confidence, quality_score)
VALUES
    (1, 1, 42, '51F-123.45', 0.9500, 85.20),
    (1, 2, 42, '51F-123.45', 0.9600, 87.10),
    (1, 3, 42, '51F-12345',  0.8200, 72.50),
    (1, 4, 42, '51F-123.45', 0.9550, 86.00);

-- Sample system settings
INSERT INTO system_settings (key, value, description)
VALUES
    ('violation_thresholds', '{"vote_percent_min": 70, "confidence_min": 0.85, "min_frames": 5}', 'Thresholds for confirming a violation'),
    ('traffic_light_timing', '{"red_duration_s": 30, "yellow_duration_s": 3, "green_duration_s": 27}', 'Default traffic light cycle timing'),
    ('notification_config',  '{"telegram_enabled": false, "telegram_bot_token": "", "telegram_chat_id": ""}', 'Notification settings')
ON CONFLICT (key) DO NOTHING;
