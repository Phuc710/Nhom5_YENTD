-- Migration: thêm violation_zone type và cropped_vehicle_url
-- Chạy trên Supabase SQL Editor (không cần xóa schema cũ)

-- 1. Thêm violation_zone vào zone_type check constraint
ALTER TABLE detection_zones
  DROP CONSTRAINT IF EXISTS detection_zones_zone_type_check;

ALTER TABLE detection_zones
  ADD CONSTRAINT detection_zones_zone_type_check
  CHECK (zone_type IN ('detection', 'stop_line', 'roi', 'violation_zone'));

-- 2. Thêm cộtใหม่ vào violations (ảnh crop xe và snapshot)
ALTER TABLE violations
  ADD COLUMN IF NOT EXISTS cropped_vehicle_url TEXT,
  ADD COLUMN IF NOT EXISTS stop_line_snapshot_url TEXT;

COMMENT ON COLUMN violations.cropped_vehicle_url    IS 'Vehicle crop with padding around plate bbox';
COMMENT ON COLUMN violations.stop_line_snapshot_url IS 'Full frame snapshot at the exact moment of stop line crossing';
COMMENT ON COLUMN violations.full_image_url         IS 'Main evidence image (snapshot)';
COMMENT ON COLUMN violations.cropped_plate_url      IS 'Direct plate crop for OCR display';
