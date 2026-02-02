# Complete Database Schema - Enhanced với Voting & Quality Metrics

## 📊 Overview

Database sử dụng **PostgreSQL** (Supabase) với các bảng sau:

```
cameras ← violations → detected_plates
                    → ocr_results (NEW - để voting)
                    → quality_metrics (NEW - tracking image quality)
                    
traffic_light_logs
users (NEW - cho mobile app)
```

## 🗃️ Tables Design

### 1. `cameras` - Thông Tin Camera

```sql
CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER UNIQUE NOT NULL,
    camera_name VARCHAR(100) NOT NULL,
    location VARCHAR(255) NOT NULL,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'inactive', 'maintenance'
    
    -- Thêm metadata
    mac_address VARCHAR(17),               -- AA:BB:CC:DD:EE:FF
    chip_id VARCHAR(32),                   -- ESP32 chip ID
    firmware_version VARCHAR(20),          -- v1.0.0
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sample data
INSERT INTO cameras (camera_id, camera_name, location, latitude, longitude, status)
VALUES 
    (1, 'Camera Gò Vấp', 'Ngã tư Gò Vấp', 10.8231, 106.6297, 'active'),
    (2, 'Camera Củ Chi', 'Ngã tư 22/12', 10.9765, 106.4920, 'active'),
    (3, 'Camera Hà Nội', 'Ngã tư Láng Hạ', 21.0134, 105.8076, 'active')
ON CONFLICT (camera_id) DO NOTHING;
```

### 2. `violations` - Record Vi Phạm

```sql
CREATE TABLE IF NOT EXISTS violations (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
    
    -- License plate info
    license_plate VARCHAR(20),
    confidence DECIMAL(5, 4),              -- OCR confidence (0.0 - 1.0)
    
    -- Images
    full_image_url TEXT NOT NULL,          -- Full image từ ESP32
    cropped_plate_url TEXT,                -- Cropped license plate image
    
    -- Traffic light state
    traffic_light_state VARCHAR(10) NOT NULL,  -- 'red', 'yellow', 'green'
    violation_type VARCHAR(50) DEFAULT 'red_light_violation',
    
    -- Timestamp
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,  -- Thời gian vi phạm
    
    -- Processing status
    processed BOOLEAN DEFAULT FALSE,
    
    -- NEW: Voting metadata
    vote_count INTEGER,                    -- Số lần OCR vote cho plate này
    vote_percent DECIMAL(5, 2),            -- % vote (40.0 = 40%)
    total_frames INTEGER,                  -- Tổng số frame đã xử lý
    track_id INTEGER,                      -- ID tracking của xe này
    
    -- NEW: Quality metrics
    image_quality_score DECIMAL(5, 2),     -- Overall quality (0-100)
    sharpness DECIMAL(8, 2),
    brightness DECIMAL(8, 2),
    contrast DECIMAL(8, 2),
    noise_level DECIMAL(8, 2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_violations_camera_id ON violations(camera_id);
CREATE INDEX IF NOT EXISTS idx_violations_timestamp ON violations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_violations_license_plate ON violations(license_plate);
CREATE INDEX IF NOT EXISTS idx_violations_created_at ON violations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_violations_processed ON violations(processed);
```

### 3. `detected_plates` - Tất Cả Plates Được Detect (For Analysis)

```sql
CREATE TABLE IF NOT EXISTS detected_plates (
    id SERIAL PRIMARY KEY,
    violation_id INTEGER REFERENCES violations(id) ON DELETE CASCADE,
    
    license_plate VARCHAR(20) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    
    -- Bounding box của plate trong ảnh gốc
    bbox JSONB,  -- {"x1": 100, "y1": 200, "x2": 300, "y2": 250}
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_detected_plates_violation_id ON detected_plates(violation_id);
CREATE INDEX IF NOT EXISTS idx_detected_plates_license_plate ON detected_plates(license_plate);
```

### 4. `ocr_results` - Tất Cả Kết Quả OCR (For Voting) ⭐ NEW

```sql
CREATE TABLE IF NOT EXISTS ocr_results (
    id SERIAL PRIMARY KEY,
    violation_id INTEGER REFERENCES violations(id) ON DELETE CASCADE,
    
    -- OCR info
    license_plate VARCHAR(20),
    confidence DECIMAL(5, 4),
    
    -- Frame info
    frame_id INTEGER,                      -- Frame số mấy (0, 1, 2, ...)
    track_id INTEGER,                      -- ID của xe (từ tracking)
    
    -- Plate detection bbox
    bbox JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ocr_results_violation_id ON ocr_results(violation_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_track_id ON ocr_results(track_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_license_plate ON ocr_results(license_plate);

COMMENT ON TABLE ocr_results IS 'Stores all OCR results from all frames for voting analysis';
```

### 5. `quality_metrics` - Image Quality Tracking ⭐ NEW

```sql
CREATE TABLE IF NOT EXISTS quality_metrics (
    id SERIAL PRIMARY KEY,
    violation_id INTEGER REFERENCES violations(id) ON DELETE CASCADE,
    
    frame_id INTEGER,                      -- Frame number
    
    -- Quality scores (0-100)
    overall_score DECIMAL(5, 2),
    sharpness DECIMAL(8, 2),               -- Variance of Laplacian
    brightness DECIMAL(8, 2),              -- Mean pixel value
    contrast DECIMAL(8, 2),                 -- Std deviation
    noise_level DECIMAL(8, 2),
    edge_density DECIMAL(8, 2),            -- Motion blur indicator
    
    -- Environmental conditions (optional)
    is_night BOOLEAN DEFAULT FALSE,
    is_rainy BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quality_metrics_violation_id ON quality_metrics(violation_id);

COMMENT ON TABLE quality_metrics IS 'Tracks image quality metrics for each frame';
```

### 6. `traffic_light_logs` - Log Trạng Thái Đèn

```sql
CREATE TABLE IF NOT EXISTS traffic_light_logs (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER NOT NULL REFERENCES cameras(camera_id),
    
    state VARCHAR(10) NOT NULL,            -- 'red', 'yellow', 'green'
    duration_seconds INTEGER,              -- Thời gian state này kéo dài
    
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traffic_light_logs_camera_id ON traffic_light_logs(camera_id);
CREATE INDEX IF NOT EXISTS idx_traffic_light_logs_timestamp ON traffic_light_logs(timestamp DESC);
```

### 7. `users` - User Accounts (Cho Mobile App) ⭐ NEW

```sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    
    -- Primary identifier
    license_plate VARCHAR(20) UNIQUE NOT NULL,  -- Dùng biển số làm username
    
    -- Contact info
    phone_number VARCHAR(15),
    email VARCHAR(100),
    full_name VARCHAR(100),
    
    -- Authentication
    password_hash VARCHAR(255),            -- Bcrypt hash
    
    -- Account status
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_license_plate ON users(license_plate);
CREATE INDEX IF NOT EXISTS idx_users_phone_number ON users(phone_number);

COMMENT ON TABLE users IS 'User accounts for mobile app (lookup violations by license plate)';
```

### 8. `violation_images` - Lưu Nhiều Ảnh Cho 1 Violation ⭐ NEW

```sql
CREATE TABLE IF NOT EXISTS violation_images (
    id SERIAL PRIMARY KEY,
    violation_id INTEGER NOT NULL REFERENCES violations(id) ON DELETE CASCADE,
    
    image_type VARCHAR(20) NOT NULL,       -- 'full', 'cropped_plate', 'debug'
    image_url TEXT NOT NULL,
    
    frame_id INTEGER,                      -- Frame nào (nếu có nhiều frame)
    quality_score DECIMAL(5, 2),           -- Quality của ảnh này
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_violation_images_violation_id ON violation_images(violation_id);
```

## 🔗 Relationships Diagram

```
cameras (1) ──┬─→ (N) violations
              │
              └─→ (N) traffic_light_logs

violations (1) ──┬─→ (N) detected_plates
                 ├─→ (N) ocr_results
                 ├─→ (N) quality_metrics
                 └─→ (N) violation_images

users (1) ───→ (N) violations (via license_plate lookup)
```

## 📝 Trigger Functions

### Auto-update `updated_at`

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to cameras
CREATE TRIGGER update_cameras_updated_at
BEFORE UPDATE ON cameras
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Apply to users
CREATE TRIGGER update_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
```

## 🔍 Sample Queries

### Query 1: Lấy Vi Phạm Với Plate & Camera Info

```sql
SELECT 
    v.id,
    v.license_plate,
    v.confidence,
    v.full_image_url,
    v.cropped_plate_url,
    v.timestamp,
    v.vote_count,
    v.vote_percent,
    v.image_quality_score,
    c.camera_name,
    c.location,
    c.latitude,
    c.longitude
FROM violations v
JOIN cameras c ON v.camera_id = c.camera_id
WHERE v.timestamp >= NOW() - INTERVAL '7 days'
ORDER BY v.timestamp DESC
LIMIT 100;
```

### Query 2: Tra Cứu Tất Cả Vi Phạm Theo Biển Số (Mobile App)

```sql
SELECT 
    v.id,
    v.license_plate,
    v.timestamp,
    v.full_image_url,
    v.cropped_plate_url,
    v.confidence,
    c.camera_name,
    c.location,
    c.latitude,
    c.longitude
FROM violations v
JOIN cameras c ON v.camera_id = c.camera_id
WHERE v.license_plate = '51F12345'
ORDER BY v.timestamp DESC;
```

### Query 3: Thống Kê Vi Phạm Theo Camera

```sql
SELECT 
    c.camera_name,
    c.location,
    COUNT(v.id) AS total_violations,
    COUNT(DISTINCT v.license_plate) AS unique_plates,
    AVG(v.image_quality_score) AS avg_quality,
    AVG(v.vote_percent) AS avg_vote_percent
FROM cameras c
LEFT JOIN violations v ON c.camera_id = v.camera_id
WHERE v.timestamp >= NOW() - INTERVAL '30 days'
GROUP BY c.id, c.camera_name, c.location
ORDER BY total_violations DESC;
```

### Query 4: Phân Tích OCR Voting (Debug)

```sql
SELECT 
    v.id AS violation_id,
    v.license_plate AS final_plate,
    v.vote_count,
    v.vote_percent,
    ocr.frame_id,
    ocr.license_plate AS ocr_plate,
    ocr.confidence AS ocr_confidence
FROM violations v
JOIN ocr_results ocr ON v.id = ocr.violation_id
WHERE v.id = 123
ORDER BY ocr.frame_id;
```

### Query 5: Image Quality Analysis

```sql
SELECT 
    v.id,
    v.license_plate,
    AVG(qm.overall_score) AS avg_quality,
    AVG(qm.sharpness) AS avg_sharpness,
    AVG(qm.brightness) AS avg_brightness,
    AVG(qm.contrast) AS avg_contrast,
    COUNT(qm.id) AS total_frames
FROM violations v
JOIN quality_metrics qm ON v.id = qm.violation_id
WHERE v.timestamp >= NOW() - INTERVAL '1 day'
GROUP BY v.id, v.license_plate
HAVING AVG(qm.overall_score) < 70  -- Find low quality violations
ORDER BY avg_quality ASC;
```

## 🚀 Performance Optimization

### Indexes

```sql
-- Composite indexes for common queries
CREATE INDEX idx_violations_camera_timestamp 
ON violations(camera_id, timestamp DESC);

CREATE INDEX idx_violations_plate_timestamp 
ON violations(license_plate, timestamp DESC);

-- Partial indexes cho active cameras
CREATE INDEX idx_active_cameras 
ON cameras(camera_id) 
WHERE status = 'active';

-- Index cho quality threshold
CREATE INDEX idx_high_quality_violations 
ON violations(image_quality_score) 
WHERE image_quality_score >= 70;
```

### Partitioning (Production - Scale)

```sql
-- Partition violations by month
CREATE TABLE violations_2026_02 PARTITION OF violations
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE violations_2026_03 PARTITION OF violations
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- Auto-create partitions (cron job hoặc trigger)
```

## 📊 Data Retention Policy

```sql
-- Delete old violations (keep 90 days)
DELETE FROM violations
WHERE timestamp < NOW() - INTERVAL '90 days';

-- Archive old data
INSERT INTO violations_archive
SELECT * FROM violations
WHERE timestamp < NOW() - INTERVAL '90 days';

-- Vacuum
VACUUM ANALYZE violations;
```

## ✅ Complete Schema Script

**`database/schema_enhanced.sql`**:

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Cameras table
CREATE TABLE IF NOT EXISTS cameras (...);  -- Full definition above

-- Violations table
CREATE TABLE IF NOT EXISTS violations (...);

-- Detected plates
CREATE TABLE IF NOT EXISTS detected_plates (...);

-- OCR results (NEW)
CREATE TABLE IF NOT EXISTS ocr_results (...);

-- Quality metrics (NEW)
CREATE TABLE IF NOT EXISTS quality_metrics (...);

-- Traffic light logs
CREATE TABLE IF NOT EXISTS traffic_light_logs (...);

-- Users (NEW)
CREATE TABLE IF NOT EXISTS users (...);

-- Violation images (NEW)
CREATE TABLE IF NOT EXISTS violation_images (...);

-- Indexes (ALL)
CREATE INDEX ...;

-- Triggers
CREATE TRIGGER ...;

-- Sample data
INSERT INTO cameras ...;

-- Comments
COMMENT ON TABLE violations IS '...';
```

---

## 🎯 Key Improvements

1. ✅ **`ocr_results`** table - Lưu tất cả OCR để voting
2. ✅ **`quality_metrics`** table - Track image quality
3. ✅ **`users`** table - Mobile app authentication
4. ✅ **`violation_images`** table - Multi-image support
5. ✅ Added **voting metadata** vào `violations` table
6. ✅ Performance indexes
7. ✅ Comprehensive sample queries
