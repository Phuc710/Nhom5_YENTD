# Database Setup (Supabase)

## 1. Tạo Supabase Project

1. Vào [supabase.com](https://supabase.com) → **New Project**
2. Chọn region gần Việt Nam (Singapore)
3. Lưu lại **Project URL** và **service_role key**

## 2. Chạy Schema

Vào **SQL Editor** trên Supabase Dashboard:

1. Copy nội dung `schema.sql` → chạy
2. Copy nội dung `seed.sql` → chạy (sample data)

## 3. Cấu hình Backend

Thêm vào file `.env` ở thư mục gốc project:

```env
TRAFFIC_SUPABASE_URL=https://your-project.supabase.co
TRAFFIC_SUPABASE_KEY=eyJhbGciOiJIUzI1NiIs...   # service_role key
```

## 4. Storage Bucket (optional)

Nếu muốn lưu ảnh vi phạm lên Supabase Storage:

1. Dashboard → **Storage** → **New Bucket**: `violations`
2. Set bucket policy: public read, service_role write

## Bảng dữ liệu

| Table | Mô tả |
|-------|-------|
| `cameras` | Danh sách camera (ESP32-S3) |
| `camera_provisioning` | Thông tin runtime từ ESP32/ThingsBoard |
| `detection_zones` | Vùng phát hiện cho từng camera |
| `violations` | Bản ghi vi phạm giao thông |
| `ocr_results` | Lịch sử OCR voting per-frame |
| `system_settings` | Cấu hình hệ thống (MQTT, retention, etc.) |

## Views

| View | Mô tả |
|------|-------|
| `view_violations_full` | Violations + camera info + provisioning |
| `view_daily_stats` | Thống kê vi phạm theo ngày/camera |
| `view_camera_summary` | Tổng hợp camera + provisioning + violation count |
