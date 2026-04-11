-- ================================================================
-- MIGRATION: Add payment support for Android citizen app
-- Run in Supabase SQL Editor
-- ================================================================

-- ── 1. Thêm cột chuẩn hóa biển số vào violations ──────────────
ALTER TABLE violations
  ADD COLUMN IF NOT EXISTS license_plate_normalized VARCHAR(20),
  ADD COLUMN IF NOT EXISTS fine_amount              INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS payment_status           VARCHAR(20) DEFAULT 'unpaid'
    CHECK (payment_status IN ('unpaid', 'pending', 'paid', 'failed')),
  ADD COLUMN IF NOT EXISTS paid_at                  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS payment_ref              VARCHAR(50);

-- Backfill license_plate_normalized từ dữ liệu hiện có
UPDATE violations
SET license_plate_normalized = UPPER(REGEXP_REPLACE(license_plate, '[^A-Z0-9]', '', 'gi'))
WHERE license_plate IS NOT NULL AND license_plate_normalized IS NULL;

-- Trigger auto-normalize khi insert/update
CREATE OR REPLACE FUNCTION fn_normalize_plate()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.license_plate_normalized :=
    UPPER(REGEXP_REPLACE(COALESCE(NEW.license_plate, ''), '[^A-Z0-9]', '', 'g'));
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_normalize_plate ON violations;
CREATE TRIGGER trg_normalize_plate
  BEFORE INSERT OR UPDATE OF license_plate ON violations
  FOR EACH ROW EXECUTE FUNCTION fn_normalize_plate();

-- Index để query nhanh theo biển số
CREATE INDEX IF NOT EXISTS idx_viol_plate_norm ON violations(license_plate_normalized);
CREATE INDEX IF NOT EXISTS idx_viol_payment_status ON violations(payment_status);

-- ── 2. Bảng violation_payments ─────────────────────────────────
CREATE TABLE IF NOT EXISTS violation_payments (
  id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  violation_id          INTEGER NOT NULL REFERENCES violations(id) ON DELETE CASCADE,
  license_plate         VARCHAR(20) NOT NULL,
  amount                INTEGER NOT NULL DEFAULT 0,
  status                VARCHAR(20) NOT NULL DEFAULT 'created'
    CHECK (status IN ('created', 'pending', 'paid', 'expired', 'failed', 'cancelled')),
  payment_code          VARCHAR(30) UNIQUE NOT NULL,
  transfer_content      TEXT,
  vietqr_payload        JSONB,
  vietqr_image_url      TEXT,
  bank_account          VARCHAR(30) DEFAULT '0332282868',
  bank_name             VARCHAR(50) DEFAULT 'MB',
  bank_bin              VARCHAR(10) DEFAULT '970422',
  sepay_transaction_id  VARCHAR(100),
  sepay_reference_code  VARCHAR(100),
  raw_response          JSONB,
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  confirmed_at          TIMESTAMPTZ,
  expired_at            TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours'),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE violation_payments IS 'Payment records for traffic violations — VietQR + SePay';
COMMENT ON COLUMN violation_payments.payment_code IS 'Mã nộp phạt duy nhất: VP + 6 digit, VD: VP123456';
COMMENT ON COLUMN violation_payments.transfer_content IS 'Nội dung CK chuẩn: NOPPHAT VP123456';
COMMENT ON COLUMN violation_payments.bank_bin IS 'BIN ngân hàng cho VietQR API';

CREATE INDEX IF NOT EXISTS idx_payments_violation_id ON violation_payments(violation_id);
CREATE INDEX IF NOT EXISTS idx_payments_plate        ON violation_payments(license_plate);
CREATE INDEX IF NOT EXISTS idx_payments_status       ON violation_payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_code         ON violation_payments(payment_code);

-- Trigger updated_at
DROP TRIGGER IF EXISTS trg_payments_updated_at ON violation_payments;
CREATE TRIGGER trg_payments_updated_at
  BEFORE UPDATE ON violation_payments
  FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ── 3. Bảng plate_sessions (optional — lưu lịch sử tra cứu) ──
CREATE TABLE IF NOT EXISTS plate_sessions (
  id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  license_plate           VARCHAR(20) NOT NULL,
  license_plate_normalized VARCHAR(20),
  device_id               VARCHAR(100),
  last_login_at           TIMESTAMPTZ DEFAULT NOW(),
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_plate ON plate_sessions(license_plate_normalized);

DROP TRIGGER IF EXISTS trg_session_normalize ON plate_sessions;
CREATE TRIGGER trg_session_normalize
  BEFORE INSERT OR UPDATE OF license_plate ON plate_sessions
  FOR EACH ROW
  EXECUTE FUNCTION fn_normalize_plate();

-- ── 4. Cập nhật view_violations_full để thêm payment info ─────
DROP VIEW IF EXISTS view_violations_full CASCADE;

CREATE OR REPLACE VIEW view_violations_full
WITH (security_invoker = true)
AS
SELECT
  v.id,
  v.license_plate,
  v.license_plate_normalized,
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
  v.fine_amount,
  v.payment_status,
  v.paid_at,
  v.payment_ref,
  v.created_at,
  c.camera_id,
  fn_camera_display_name(
    c.camera_name, c.tb_device_name,
    p.device_name, p.project_name, p.tb_device_name, c.camera_id
  ) AS camera_name,
  c.location,
  c.latitude,
  c.longitude,
  fn_stream_url(
    c.stream_url, p.stream_scheme,
    COALESCE(p.stream_host, p.ip_address),
    p.stream_port, p.stream_path
  ) AS stream_url,
  COALESCE(c.tb_device_name, p.tb_device_name) AS tb_device_name,
  p.device_name,
  p.project_name,
  p.device_model,
  p.resolution,
  p.ip_address,
  p.fw_version,
  p.last_seen_at,
  -- Payment join (latest payment for this violation)
  vp.id            AS payment_id,
  vp.payment_code,
  vp.transfer_content,
  vp.amount        AS payment_amount,
  vp.status        AS payment_status_detail,
  vp.vietqr_image_url,
  vp.bank_account,
  vp.bank_name,
  vp.bank_bin,
  vp.confirmed_at  AS payment_confirmed_at,
  vp.expired_at    AS payment_expired_at
FROM violations v
JOIN cameras c ON v.camera_id = c.camera_id
LEFT JOIN camera_provisioning p ON p.camera_id = c.camera_id
LEFT JOIN LATERAL (
  SELECT * FROM violation_payments
  WHERE violation_id = v.id
  ORDER BY created_at DESC LIMIT 1
) vp ON true;

-- ── 5. RLS cho bảng mới ────────────────────────────────────────
ALTER TABLE violation_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE plate_sessions     ENABLE ROW LEVEL SECURITY;

-- App Android đọc payment theo violation_id (anon key OK)
DROP POLICY IF EXISTS public_read_payments ON violation_payments;
CREATE POLICY public_read_payments ON violation_payments
  FOR SELECT USING (true);

-- Chỉ service_role mới tạo/cập nhật payment
DROP POLICY IF EXISTS service_write_payments ON violation_payments;
CREATE POLICY service_write_payments ON violation_payments
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- App Android ghi session (anon)
DROP POLICY IF EXISTS anon_insert_sessions ON plate_sessions;
CREATE POLICY anon_insert_sessions ON plate_sessions
  FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS anon_read_sessions ON plate_sessions;
CREATE POLICY anon_read_sessions ON plate_sessions
  FOR SELECT USING (true);

-- ── 6. Fine amount defaults theo loại vi phạm ─────────────────
-- Cập nhật fine_amount dựa theo violation_type nếu chưa có
UPDATE violations
SET fine_amount = CASE
  WHEN violation_type = 'red_light'  THEN 1200000
  WHEN violation_type = 'speeding'   THEN 800000
  WHEN violation_type = 'wrong_lane' THEN 300000
  ELSE 500000
END
WHERE fine_amount = 0 OR fine_amount IS NULL;

-- ── 7. Function: tạo payment code tự động ─────────────────────
CREATE OR REPLACE FUNCTION generate_payment_code()
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
  code TEXT;
  attempt INT := 0;
BEGIN
  LOOP
    code := 'VP' || LPAD((FLOOR(RANDOM() * 999999 + 1))::TEXT, 6, '0');
    IF NOT EXISTS (SELECT 1 FROM violation_payments WHERE payment_code = code) THEN
      RETURN code;
    END IF;
    attempt := attempt + 1;
    IF attempt > 10 THEN
      code := 'VP' || TO_CHAR(NOW(), 'SSMS') || LPAD((FLOOR(RANDOM() * 99))::TEXT, 2, '0');
      RETURN code;
    END IF;
  END LOOP;
END;
$$;

-- Xác nhận hoàn tất
SELECT 'Migration completed successfully' AS result;
