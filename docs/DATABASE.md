# Database Schema Reference

> **Database**: Supabase / PostgreSQL  
> **Timezone lưu**: UTC (convert sang `Asia/Ho_Chi_Minh` khi hiển thị)  
> **Auth**: Row Level Security (RLS) — public đọc được, service_role mới ghi được

---

## Sơ đồ quan hệ

```
cameras (1) ──────────── (1) camera_provisioning
   │
   ├──── (1:N) ──── detection_zones
   │
   └──── (1:N) ──── violations (N) ──── (1:N) ──── ocr_results

system_settings (độc lập)
```

---

## Bảng: `cameras`

> Registry tĩnh của từng camera vật lý (ESP32-S3). Backend và dashboard quản lý.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | SERIAL PK | Auto-increment nội bộ |
| `camera_id` | INTEGER UNIQUE | **ID nghiệp vụ** — dùng trong toàn hệ thống |
| `camera_name` | VARCHAR(100) | Tên hiển thị, VD: "Cam Ngã Tư 1" |
| `location` | VARCHAR(255) | Vị trí địa lý, VD: "Ngã tư Hàng Xanh" |
| `latitude` | DECIMAL(10,7) | Tọa độ GPS — latitude |
| `longitude` | DECIMAL(10,7) | Tọa độ GPS — longitude |
| `stream_url` | VARCHAR(512) | URL stream thủ công. `NULL` → tự build từ provisioning |
| `description` | TEXT | Mô tả tùy chọn |
| `tb_device_name` | VARCHAR(255) | Tên thiết bị trên ThingsBoard |
| `status` | VARCHAR(20) | `active` / `inactive` / `error` |
| `confidence_threshold` | DECIMAL(5,4) | Ngưỡng confidence ALPR cho camera này (default: 0.5) |
| `operation_mode` | VARCHAR(50) | `balanced` / `performance` / `accuracy` |
| `rotate_180` | BOOLEAN | Xoay frame 180° (gắn ngược) |
| `flip_horizontal` | BOOLEAN | Lật ngang frame |
| `created_at` | TIMESTAMPTZ | UTC |
| `updated_at` | TIMESTAMPTZ | UTC — tự cập nhật qua trigger |

**Ví dụ:**
```json
{
  "camera_id": 1,
  "camera_name": "Cam Ngã Tư Hàng Xanh",
  "location": "Ngã tư Hàng Xanh, Q. Bình Thạnh",
  "latitude": 10.8040372,
  "longitude": 106.7134500,
  "status": "active",
  "confidence_threshold": 0.6
}
```

---

## Bảng: `camera_provisioning`

> Thông tin runtime động — ESP32-S3 tự đăng ký khi boot. 1 camera → 1 provisioning.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | UUID PK | |
| `camera_id` | INTEGER FK → cameras | Liên kết với camera |
| `device_name` | VARCHAR(255) | Tên thiết bị ESP32 đặt trong firmware |
| `project_name` | VARCHAR(255) | Tên project (từ firmware) |
| `tb_device_id` | VARCHAR(255) | ThingsBoard Device ID |
| `tb_device_name` | VARCHAR(255) | ThingsBoard Device Name |
| `device_model` | VARCHAR(100) | ESP32-S3-DevKitC-1 |
| `wifi_ssid` | VARCHAR(255) | WiFi đang kết nối |
| `resolution` | VARCHAR(50) | VD: "640x480" |
| `mac_address` | VARCHAR(17) | MAC address, VD: "AA:BB:CC:DD:EE:FF" |
| `fw_version` | VARCHAR(50) | Firmware version |
| `idf_version` | VARCHAR(50) | ESP-IDF version |
| `ip_address` | VARCHAR(45) | IP local |
| `stream_scheme` | VARCHAR(10) | `http` / `rtsp` |
| `stream_host` | VARCHAR(255) | Host/IP của stream |
| `stream_port` | INTEGER | Port (default: 81) |
| `stream_path` | VARCHAR(255) | Path (default: `/stream`) |
| `stream_snapshot_path` | VARCHAR(255) | Snapshot path (default: `/snapshot`) |
| `online` | BOOLEAN | Đang online không |
| `last_seen_at` | TIMESTAMPTZ | Lần cuối nhận MQTT heartbeat |
| `last_boot_at` | TIMESTAMPTZ | Lần cuối reboot |
| `access_token` | VARCHAR(255) | ThingsBoard access token |
| `extra_attributes` | JSONB | JSON mở rộng cho tương lai |
| `updated_at` | TIMESTAMPTZ | Tự cập nhật qua trigger |

> **Lưu ý**: `stream_url` trong response được build tự động bởi function `fn_stream_url()`:  
> `{scheme}://{host_or_ip}:{port}{path}` → VD: `http://192.168.1.50:81/stream`

---

## Bảng: `detection_zones`

> Vùng phát hiện vi phạm trên camera. Mỗi camera có thể có nhiều zone.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | UUID PK | |
| `camera_id` | INTEGER FK | Camera sở hữu zone |
| `zone_name` | VARCHAR(100) | Tên zone, VD: "zone-1" |
| `x` | INTEGER | Tọa độ X góc trên trái (pixel) |
| `y` | INTEGER | Tọa độ Y góc trên trái (pixel) |
| `width` | INTEGER | Chiều rộng zone (pixel) |
| `height` | INTEGER | Chiều cao zone (pixel) |
| `zone_type` | VARCHAR(50) | Loại zone (xem bên dưới) |
| `active` | BOOLEAN | Zone đang hoạt động |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Zone types:**

| Giá trị | Ý nghĩa |
|---------|---------|
| `detection` | Vùng detect xe (polygon) |
| `stop_line` | Vạch dừng xe |
| `violation_zone` | Vùng sau vạch — vào đây = vi phạm |
| `roi` | Region of Interest — chỉ nhìn vùng này |

> **Lưu ý**: Tọa độ zone trong DB là pixel tuyệt đối. Trong `app_settings.json` là tọa độ tỉ lệ (0.0-1.0).

---

## Bảng: `violations`

> **Bảng chính** — lưu mỗi lần vi phạm bị phát hiện.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | SERIAL PK | Violation ID |
| `camera_id` | INTEGER FK | Camera phát hiện |
| `license_plate` | VARCHAR(20) | Biển số đã nhận dạng, VD: "MP04CF0655" |
| `confidence` | DECIMAL(5,4) | Độ tin cậy OCR (0.0000 – 1.0000) |
| `full_image_url` | TEXT NOT NULL | **Ảnh gốc full frame** (không overlay) — WebP |
| `cropped_vehicle_url` | TEXT | **Ảnh xe** đã crop + khung đỏ drawn — WebP |
| `cropped_plate_url` | TEXT | **Ảnh biển số** phóng to + viền vàng — WebP |
| `stop_line_snapshot_url` | TEXT | Ảnh lúc xe vượt vạch |
| `violation_type` | VARCHAR(50) | `red_light` / `wrong_lane` / `speeding` |
| `traffic_light_state` | VARCHAR(10) | `red` / `yellow` / `green` |
| `timestamp` | TIMESTAMPTZ NOT NULL | Thời điểm vi phạm (UTC) |
| `vote_count` | SMALLINT | Số frame tham gia voting biển số |
| `vote_percent` | DECIMAL(5,2) | Tỉ lệ nhất trí (%) VD: 91.7 |
| `total_frames` | SMALLINT | Tổng số frame xe trong luồng |
| `track_id` | INTEGER | DeepSORT track ID |
| `image_quality_score` | DECIMAL(5,2) | Điểm chất lượng ảnh |
| `bbox_x` | INTEGER | Bounding box xe — X |
| `bbox_y` | INTEGER | Bounding box xe — Y |
| `bbox_w` | INTEGER | Bounding box xe — Width |
| `bbox_h` | INTEGER | Bounding box xe — Height |
| `processed` | BOOLEAN | Đã xử lý xong chưa |
| `processing_time_ms` | INTEGER | Thời gian xử lý backend (ms) |
| `created_at` | TIMESTAMPTZ | Lúc insert vào DB |
| `updated_at` | TIMESTAMPTZ | |

**Ảnh 3 loại (tương ứng 3 folder local):**

| URL field | Folder local | Supabase path | Nội dung |
|-----------|-------------|---------------|---------|
| `full_image_url` | `data/violations/original/` | `original/cam1/...` | Full frame, không overlay |
| `cropped_vehicle_url` | `data/violations/vehicle/` | `vehicle/cam1/...` | Crop xe + bbox đỏ |
| `cropped_plate_url` | `data/violations/plate/` | `plate/cam1/...` | Biển số phóng to |

---

## Bảng: `ocr_results`

> Lịch sử voting OCR từng frame — dùng để debug và phân tích độ chính xác.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | SERIAL PK | |
| `violation_id` | INTEGER FK → violations | Vi phạm liên quan |
| `frame_id` | INTEGER | Thứ tự frame |
| `track_id` | INTEGER | Track ID của xe |
| `license_plate` | VARCHAR(20) | Kết quả OCR của frame này |
| `confidence` | DECIMAL(5,4) | Confidence của frame này |
| `quality_score` | DECIMAL(5,2) | Chất lượng ảnh frame |
| `created_at` | TIMESTAMPTZ | |

---

## Bảng: `system_settings`

> Key-value store cho config toàn hệ thống.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `key` | VARCHAR(100) PK | Key định danh |
| `value` | JSONB | Giá trị (JSON) |
| `description` | TEXT | Mô tả |
| `updated_at` | TIMESTAMPTZ | |

**Các key mặc định:**

| Key | Value mặc định | Ý nghĩa |
|-----|---------------|---------|
| `mqtt_config` | `{"host": "thingsboard.cloud", "port": 1883}` | ThingsBoard MQTT |
| `data_retention` | `{"days": 30}` | Xóa vi phạm cũ sau N ngày |

---

## Views

### `view_violations_full`

JOIN `violations` + `cameras` + `camera_provisioning`. Trả thêm:
- `timestamp_vn` — thời gian theo múi giờ VN
- `camera_name` — tên tự động (logic ưu tiên nhiều nguồn)
- `stream_url` — URL stream đã build sẵn
- Tất cả thông tin camera + provisioning

### `view_daily_stats`

Thống kê số vi phạm theo ngày + camera:
```sql
date_vn | camera_id | violation_count | unique_plates | avg_confidence | avg_quality
```

### `view_camera_summary`

Tổng hợp camera + provisioning + số vi phạm:
- `violations_today` — vi phạm hôm nay
- `violations_total` — tổng vi phạm
- Toàn bộ thông tin provisioning (IP, MAC, firmware, online status, ...)

---

## Indexes (tối ưu query)

| Index | Dùng khi |
|-------|---------|
| `idx_viol_timestamp` | Query violations mới nhất |
| `idx_viol_plate` | Tìm kiếm theo biển số |
| `idx_viol_cam_ts` | Lọc theo camera + thời gian |
| `idx_prov_online_seen` | Tìm camera đang online |
| `idx_prov_mac` | Tìm camera theo MAC address |

---

## RLS (Row Level Security)

| Bảng | Public (anon) | service_role |
|------|-------------|-------------|
| `cameras` | SELECT | INSERT, UPDATE |
| `violations` | SELECT | INSERT, UPDATE |
| `camera_provisioning` | SELECT | ALL |
| `detection_zones` | SELECT | ALL |
| `ocr_results` | – | INSERT |
| `system_settings` | SELECT | ALL |

> Backend dùng **service_role key** để ghi. Frontend/mobile dùng **anon key** để đọc.

---

## Supabase Storage — bucket `violations`

```
violations/           ← bucket public (read), service_role (write)
├── original/         ← Ảnh gốc full frame
│   └── {timestamp}_{uid}_t{track_id}.webp
├── vehicle/          ← Crop xe + bbox đỏ
│   └── {timestamp}_{uid}_t{track_id}.webp
└── plate/            ← Biển số phóng to + viền vàng
    └── {timestamp}_{uid}_t{track_id}.webp
```

Tạo bucket trong Supabase Dashboard → Storage → New bucket → tên `violations` → Public.
