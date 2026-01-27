# Database Schema

## Tổng Quan

Database: **Supabase (PostgreSQL)**

Tables:
- `cameras` - Thông tin camera
- `violations` - Vi phạm giao thông
- `detected_plates` - Tất cả biển số detect được
- `traffic_light_logs` - Lịch sử đèn giao thông

## Table: cameras

Lưu thông tin các camera ESP32-CAM.

### Schema

```sql
CREATE TABLE cameras (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER UNIQUE NOT NULL,
    camera_name VARCHAR(255) NOT NULL,
    location TEXT,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Columns

| Column | Type | Nullable | Default | Mô tả |
|--------|------|----------|---------|-------|
| `id` | SERIAL | NO | auto | Primary key |
| `camera_id` | INTEGER | NO | - | ID camera (1, 2, 3) |
| `camera_name` | VARCHAR(255) | NO | - | Tên camera |
| `location` | TEXT | YES | - | Địa điểm |
| `latitude` | DECIMAL(10,8) | YES | - | Vĩ độ |
| `longitude` | DECIMAL(11,8) | YES | - | Kinh độ |
| `status` | VARCHAR(50) | YES | 'active' | Trạng thái |
| `created_at` | TIMESTAMP | YES | NOW() | Ngày tạo |
| `updated_at` | TIMESTAMP | YES | NOW() | Ngày cập nhật |

### Indexes

```sql
CREATE INDEX idx_cameras_camera_id ON cameras(camera_id);
CREATE INDEX idx_cameras_status ON cameras(status);
```

### Sample Data

```sql
INSERT INTO cameras (camera_id, camera_name, location, latitude, longitude) VALUES
(1, 'Camera Gò Vấp', 'Ngã tư Phan Văn Trị - Quang Trung, Gò Vấp, TP.HCM', 10.8231, 106.6297),
(2, 'Camera Củ Chi', 'Ngã tư Tỉnh Lộ 8 - Quốc Lộ 22, Củ Chi, TP.HCM', 10.9742, 106.4937),
(3, 'Camera Hà Nội', 'Ngã tư Láng Hạ - Thái Hà, Đống Đa, Hà Nội', 21.0168, 105.8143);
```

---

## Table: violations

Lưu các vi phạm giao thông.

### Schema

```sql
CREATE TABLE violations (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER NOT NULL REFERENCES cameras(camera_id),
    image_url TEXT NOT NULL,
    plate_image_url TEXT,
    license_plate VARCHAR(20),
    confidence DECIMAL(5, 4),
    traffic_light_state VARCHAR(20),
    violation_type VARCHAR(100) DEFAULT 'red_light_violation',
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Columns

| Column | Type | Nullable | Default | Mô tả |
|--------|------|----------|---------|-------|
| `id` | SERIAL | NO | auto | Primary key |
| `camera_id` | INTEGER | NO | - | Foreign key → cameras |
| `image_url` | TEXT | NO | - | URL ảnh gốc |
| `plate_image_url` | TEXT | YES | - | URL ảnh biển số crop |
| `license_plate` | VARCHAR(20) | YES | - | Biển số xe |
| `confidence` | DECIMAL(5,4) | YES | - | Độ chính xác (0-1) |
| `traffic_light_state` | VARCHAR(20) | YES | - | red/yellow/green |
| `violation_type` | VARCHAR(100) | YES | 'red_light_violation' | Loại vi phạm |
| `timestamp` | TIMESTAMP | NO | - | Thời gian vi phạm |
| `created_at` | TIMESTAMP | YES | NOW() | Ngày tạo record |
| `updated_at` | TIMESTAMP | YES | NOW() | Ngày cập nhật |

### Indexes

```sql
CREATE INDEX idx_violations_camera_id ON violations(camera_id);
CREATE INDEX idx_violations_timestamp ON violations(timestamp DESC);
CREATE INDEX idx_violations_license_plate ON violations(license_plate);
CREATE INDEX idx_violations_created_at ON violations(created_at DESC);
```

### Triggers

Auto-update `updated_at`:

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_violations_updated_at
    BEFORE UPDATE ON violations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

## Table: detected_plates

Lưu **TẤT CẢ** biển số detect được (kể cả duplicate).

### Schema

```sql
CREATE TABLE detected_plates (
    id SERIAL PRIMARY KEY,
    violation_id INTEGER REFERENCES violations(id) ON DELETE CASCADE,
    license_plate VARCHAR(20),
    confidence DECIMAL(5, 4),
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    bbox_x2 INTEGER,
    bbox_y2 INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Columns

| Column | Type | Nullable | Mô tả |
|--------|------|----------|-------|
| `id` | SERIAL | NO | Primary key |
| `violation_id` | INTEGER | YES | Foreign key → violations |
| `license_plate` | VARCHAR(20) | YES | Biển số |
| `confidence` | DECIMAL(5,4) | YES | Độ chính xác |
| `bbox_x1` | INTEGER | YES | Bounding box X1 |
| `bbox_y1` | INTEGER | YES | Bounding box Y1 |
| `bbox_x2` | INTEGER | YES | Bounding box X2 |
| `bbox_y2` | INTEGER | YES | Bounding box Y2 |
| `created_at` | TIMESTAMP | YES | Ngày tạo |

### Indexes

```sql
CREATE INDEX idx_detected_plates_violation_id ON detected_plates(violation_id);
CREATE INDEX idx_detected_plates_license_plate ON detected_plates(license_plate);
```

---

## Table: traffic_light_logs

Lưu lịch sử thay đổi trạng thái đèn giao thông.

### Schema

```sql
CREATE TABLE traffic_light_logs (
    id SERIAL PRIMARY KEY,
    traffic_light_id INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL,
    operation_mode VARCHAR(50),
    timestamp TIMESTAMP DEFAULT NOW()
);
```

### Columns

| Column | Type | Nullable | Mô tả |
|--------|------|----------|-------|
| `id` | SERIAL | NO | Primary key |
| `traffic_light_id` | INTEGER | NO | ID đèn (1, 2, 3) |
| `state` | VARCHAR(20) | NO | red/yellow/green |
| `operation_mode` | VARCHAR(50) | YES | normal/emergency_red/emergency_green |
| `timestamp` | TIMESTAMP | YES | Thời gian |

### Indexes

```sql
CREATE INDEX idx_traffic_light_logs_timestamp ON traffic_light_logs(timestamp DESC);
CREATE INDEX idx_traffic_light_logs_light_id ON traffic_light_logs(traffic_light_id);
```

---

## Relationships

```
cameras (1) ──< (N) violations
violations (1) ──< (N) detected_plates
```

### Foreign Keys

```sql
ALTER TABLE violations
    ADD CONSTRAINT fk_violations_camera
    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id);

ALTER TABLE detected_plates
    ADD CONSTRAINT fk_detected_plates_violation
    FOREIGN KEY (violation_id) REFERENCES violations(id)
    ON DELETE CASCADE;
```

---

## Queries Thường Dùng

### 1. Vi phạm hôm nay

```sql
SELECT * FROM violations
WHERE DATE(timestamp) = CURRENT_DATE
ORDER BY timestamp DESC;
```

### 2. Top camera có nhiều vi phạm nhất

```sql
SELECT 
    c.camera_name,
    COUNT(v.id) as violation_count
FROM cameras c
LEFT JOIN violations v ON c.camera_id = v.camera_id
GROUP BY c.camera_id, c.camera_name
ORDER BY violation_count DESC;
```

### 3. Vi phạm theo giờ

```sql
SELECT 
    EXTRACT(HOUR FROM timestamp) as hour,
    COUNT(*) as count
FROM violations
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour;
```

### 4. Tìm biển số

```sql
SELECT * FROM violations
WHERE license_plate ILIKE '%51A%'
ORDER BY timestamp DESC;
```

### 5. Duplicate detection

```sql
SELECT 
    camera_id,
    license_plate,
    COUNT(*) as count
FROM violations
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY camera_id, license_plate
HAVING COUNT(*) > 1;
```

---

## Maintenance

### Vacuum

```sql
VACUUM ANALYZE violations;
VACUUM ANALYZE detected_plates;
```

### Reindex

```sql
REINDEX TABLE violations;
REINDEX TABLE detected_plates;
```

### Cleanup Old Data

```sql
-- Xóa vi phạm > 1 năm
DELETE FROM violations
WHERE created_at < NOW() - INTERVAL '1 year';
```

---

## Backup

### Manual Backup (pg_dump)

```bash
pg_dump -h your-db-host -U postgres -d traffic_db > backup.sql
```

### Restore

```bash
psql -h your-db-host -U postgres -d traffic_db < backup.sql
```

### Supabase Auto Backup

Supabase tự động backup hàng ngày. Restore từ dashboard.

---

## Performance Optimization

### 1. Partition by Date

Nếu có nhiều data, partition table `violations` theo tháng:

```sql
CREATE TABLE violations_2026_01 PARTITION OF violations
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
```

### 2. Materialized Views

Tạo view cho stats:

```sql
CREATE MATERIALIZED VIEW stats_daily AS
SELECT 
    DATE(timestamp) as date,
    camera_id,
    COUNT(*) as violation_count
FROM violations
GROUP BY DATE(timestamp), camera_id;

-- Refresh mỗi ngày
REFRESH MATERIALIZED VIEW stats_daily;
```

### 3. Connection Pooling

Dùng PgBouncer hoặc Supabase connection pooler.

---

## Security

### Row Level Security (RLS)

```sql
-- Enable RLS
ALTER TABLE violations ENABLE ROW LEVEL SECURITY;

-- Policy: Chỉ cho phép đọc
CREATE POLICY "Allow read access" ON violations
    FOR SELECT
    USING (true);

-- Policy: Chỉ backend có thể insert
CREATE POLICY "Allow backend insert" ON violations
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');
```

### Encryption

Supabase tự động encrypt data at rest.

---

## Monitoring

### Table Size

```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Index Usage

```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
```

### Slow Queries

```sql
SELECT 
    query,
    calls,
    total_time,
    mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

---

## Migration Script

Full schema creation:

```sql
-- Create tables
CREATE TABLE cameras (...);
CREATE TABLE violations (...);
CREATE TABLE detected_plates (...);
CREATE TABLE traffic_light_logs (...);

-- Create indexes
CREATE INDEX ...;

-- Create triggers
CREATE TRIGGER ...;

-- Insert sample data
INSERT INTO cameras ...;
```

Chạy trong Supabase SQL Editor.
