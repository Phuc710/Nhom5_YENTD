# Kiến Trúc Hệ Thống

## Tổng Quan

Hệ thống phát hiện vi phạm giao thông gồm 5 thành phần chính:

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  ESP32-CAM #1   │         │   ESP32 Đèn      │         │  ThingsBoard    │
│  (Gò Vấp)       ├────────►│   Giao Thông #1  ├────────►│  IoT Platform   │
│                 │  MQTT   │                  │  MQTT   │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
         │                                                        │
         │ HTTP POST                                              │ Giám sát
         ▼                                                        ▼
┌─────────────────────────────────────────┐         ┌─────────────────────┐
│         Backend Python (VPS)            │         │   Web Dashboard     │
│  ┌───────────────────────────────────┐  │         │                     │
│  │  FastAPI REST API                 │  │◄────────┤  - Danh sách vi phạm│
│  │  /api/upload                      │  │  HTTP   │  - Thống kê         │
│  │  /api/violations                  │  │         │  - Tìm kiếm         │
│  └───────────────────────────────────┘  │         └─────────────────────┘
│  ┌───────────────────────────────────┐  │
│  │  YOLO ML Detection                │  │
│  │  - Detector (nano_61.pt)          │  │
│  │  - OCR (nano_62.pt)               │  │
│  │  - Chống trùng lặp                │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Supabase Database                │  │
│  │  - violations                     │  │
│  │  - detected_plates                │  │
│  │  - cameras                        │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Chi Tiết Từng Thành Phần

### 1. ESP32-CAM (x3 thiết bị)

**Chức năng**: Chụp ảnh khi đèn đỏ

**Quy trình hoạt động**:
1. Khởi động → WiFiManager (AP mode hoặc kết nối WiFi đã lưu)
2. Provision với ThingsBoard → nhận device token
3. Kết nối MQTT broker
4. Request shared attributes (`camera_id`, `capture_interval`)
5. Vòng lặp chính:
   - Nếu đèn ĐỎ → chụp ảnh mỗi 1 giây
   - HTTP POST lên Backend API
   - Publish telemetry lên ThingsBoard

**Quản lý bộ nhớ**:
```cpp
camera_fb_t* fb = camera_capture();  // 1. Chụp
uint8_t* buffer = ps_malloc(size);   // 2. Cấp phát
// ... sử dụng buffer ...
free(buffer);                        // 3. GIẢI PHÓNG
camera_release(fb);                  // 4. TRẢ FRAME BUFFER
```

**⚠️ Quan trọng**: Luôn giải phóng bộ nhớ theo đúng thứ tự!

### 2. ESP32 Điều Khiển Đèn Giao Thông (x3 thiết bị)

**State Machine**:
```
ĐỎ (7s) → XANH (5s) → VÀNG (2s) → ĐỎ
```

**Chế độ khẩn cấp**:
- Nút 1: Chuyển sang ĐÈN ĐỎ (ấn lại → về bình thường)
- Nút 2: Chuyển sang ĐÈN XANH (ấn lại → về bình thường)

**MQTT Topics**:
- Publish: `v1/devices/me/telemetry`
  ```json
  {
    "traffic_light_state": "red",
    "operation_mode": "normal",
    "uptime_sec": 12345
  }
  ```

### 3. Backend Server (Python FastAPI)

**API Endpoints**:

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/upload` | POST | Nhận ảnh từ ESP32 |
| `/api/violations` | GET | Danh sách vi phạm |
| `/api/violations/{id}` | GET | Chi tiết vi phạm |
| `/api/violations/{id}` | DELETE | Xóa vi phạm |
| `/api/cameras` | GET | Danh sách camera |
| `/api/stats` | GET | Thống kê |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc |

**Pipeline xử lý ảnh**:
```
1. Nhận ảnh từ ESP32
   ↓
2. Lưu ảnh gốc → uploads/original/
   ↓
3. YOLO Plate Detection
   ↓
4. Với mỗi biển số phát hiện:
   - Crop vùng biển số
   - OCR đọc ký tự
   - Lưu ảnh crop → uploads/detected_plates/
   ↓
5. Kiểm tra trùng lặp:
   - Cùng camera_id + license_plate trong 5s?
   - NẾU có → Bỏ qua
   - NẾU không → Tạo record vi phạm
   ↓
6. Trả response cho ESP32
```

**Logic chống trùng lặp**:
```python
if (same_camera AND same_plate AND within_5_seconds):
    skip_creation()
else:
    create_violation()
```

### 4. Database (Supabase PostgreSQL)

**Tables**:

#### `cameras`
```sql
id, camera_id, camera_name, location, latitude, longitude, status
```

#### `violations`
```sql
id, camera_id, image_url, plate_image_url, license_plate,
confidence, traffic_light_state, violation_type, timestamp
```

#### `detected_plates`
```sql
id, violation_id, license_plate, confidence, bbox, created_at
```

**Indexes** (tối ưu truy vấn):
- `violations.camera_id`
- `violations.timestamp`
- `violations.license_plate`

### 5. ThingsBoard IoT Platform

**Device Profiles**:

1. **ESP32-CAM**
   - Auto-provisioning: Bật
   - Telemetry: `status`, `upload`, `free_heap`
   - Shared Attributes: `camera_id`, `capture_interval`

2. **Traffic Light**
   - Telemetry: `traffic_light_state`, `operation_mode`
   - RPC Commands: `setNormalMode`, `setEmergencyRed`, `setEmergencyGreen`

**Rule Chains**:
- Lưu telemetry vào time-series DB
- Cảnh báo khi device offline
- Log thay đổi trạng thái

### 6. Web Dashboard

**Trang chính**:
- Thống kê (Tổng, Hôm nay, 7 ngày, 30 ngày)
- Danh sách vi phạm
- Filter theo camera/thời gian/biển số
- Xem ảnh full size (modal)

**Tính năng**:
- Real-time statistics
- Search & filter
- Delete violations
- Xem ảnh gốc + ảnh biển số crop

## Luồng Dữ Liệu - Ví Dụ Thực Tế

### Tình huống: Xe vượt đèn đỏ tại Gò Vấp

```
1. Đèn Giao Thông #1 chuyển ĐỎ
   ├─► ESP32 Traffic Light publish MQTT:
   │   Topic: v1/devices/me/telemetry
   │   Data: {"traffic_light_state": "red"}
   │
2. ESP32-CAM #1 nhận tín hiệu đèn đỏ
   ├─► Chụp ảnh (UXGA 1600x1200)
   │
3. ESP32-CAM POST lên Backend
   ├─► POST http://vps:8000/api/upload
   │   Form data:
   │   - file: image.jpg
   │   - camera_id: 1
   │   - traffic_light_state: red
   │
4. Backend xử lý ảnh
   ├─► YOLO detector tìm biển số
   ├─► OCR đọc: "51A-12345"
   ├─► Confidence: 0.87
   │
5. Kiểm tra trùng lặp
   ├─► Query: violations WHERE
   │   camera_id=1 AND license_plate="51A-12345"
   │   AND timestamp > (now - 5s)
   ├─► Kết quả: Không trùng
   │
6. Tạo record vi phạm
   ├─► Lưu vào Supabase:
   │   {
   │     camera_id: 1,
   │     license_plate: "51A-12345",
   │     confidence: 0.87,
   │     image_url: "/uploads/original/cam1_xxx.jpg",
   │     plate_image_url: "/uploads/detected_plates/plate_xxx.jpg",
   │     timestamp: "2026-01-27 22:05:30"
   │   }
   │
7. Trả response cho ESP32-CAM
   └─► {"success": true, "violations": [...]}
```

## Cấu Trúc Mạng

```
Internet
    │
    ├─── [ThingsBoard Cloud] tcm-iot.imespro.ai
    │         └─ MQTT: 103.249.117.212:1883
    │
    ├─── [VPS Server] your-vps-ip
    │         ├─ Backend API: Port 8000
    │         └─ Web Dashboard: Port 80/443
    │
    └─── [Supabase Cloud] your-project.supabase.co
              └─ PostgreSQL Database

Mạng Cục Bộ (Ngã tư)
    │
    ├─── WiFi Router
    │      ├─ ESP32-CAM #1 (192.168.1.100)
    │      └─ ESP32 Traffic Light #1 (192.168.1.101)
```

## Bảo Mật

### Hiện tại (Demo)
- ⚠️ HTTP (không mã hóa)
- ⚠️ Không authentication
- ⚠️ Provision keys hardcode

### Khuyến nghị Production
- ✅ HTTPS cho tất cả API
- ✅ JWT authentication cho dashboard
- ✅ Lưu provision keys an toàn
- ✅ VPN cho ESP32 devices
- ✅ Supabase RLS (Row Level Security)
- ✅ Rate limiting
- ✅ Audit logs

## Tối Ưu Hiệu Năng

### Backend
- Dùng Gunicorn với 4 workers
- Nginx reverse proxy
- Cache static files
- Async/await cho I/O operations

### ESP32
- Giải phóng bộ nhớ ngay sau upload
- Sử dụng PSRAM cho frame buffer
- Timeout HTTP requests
- MQTT keepalive

### Database
- Indexes trên các cột thường query
- Partition table theo tháng
- Auto-vacuum
- Connection pooling
