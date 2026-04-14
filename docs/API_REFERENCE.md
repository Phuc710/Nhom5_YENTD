# API Reference — TrafficCam Backend

> **Base URL**: `http://localhost:8000`  
> **Docs tương tác**: `http://localhost:8000/docs` (Swagger UI)  
> **OpenAPI JSON**: `http://localhost:8000/openapi.json`  
> **Format**: Tất cả request/response là `application/json` trừ khi có ghi chú khác.  
> **Ảnh**: Tất cả ảnh trả về **WebP** format.

---

## Mục lục

1. [Health & Root](#1-health--root)
2. [ALPR — Inference](#2-alpr--inference)
3. [Stream — Camera](#3-stream--camera)
4. [Evidence — Violation Images](#4-evidence--violation-images)
5. [Violations — CRUD](#5-violations--crud)
6. [Cameras — CRUD](#6-cameras--crud)
7. [Detection Zones](#7-detection-zones)
8. [MQTT — IoT Control](#8-mqtt--iot-control)
9. [Local Settings](#9-local-settings)
10. [System Settings (DB)](#10-system-settings-db)

---

## 1. Health & Root

### `GET /`
Thông tin service và danh sách các nhóm endpoint.

**Response:**
```json
{
  "service": "TrafficCam ALPR API",
  "version": "2.0.0",
  "status": "running",
  "endpoints": {
    "docs": "/docs",
    "health": "/health",
    "predict": "/predict",
    "stream": "/stream",
    "evidence": "/evidence"
  }
}
```

---

### `GET /health`
Kiểm tra trạng thái tất cả services.

**Response:**
```json
{
  "status": "ok",
  "alpr_ready": true,
  "stream_active": false,
  "db_connected": true,
  "mqtt_connected": false,
  "local_settings_loaded": true
}
```

---

### `GET /config`
Xem cấu hình ALPR hiện tại.

**Response:**
```json
{
  "vehicle_weight": "models/vehicle/vehicle_yolov8s.pt",
  "plate_weight": "models/plate/plate_yolov8n.pt",
  "vconf": 0.6,
  "pconf": 0.25,
  "ocr_thres": 0.9,
  "read_plate": true,
  "device": "0",
  "lang": "en"
}
```

---

## 2. ALPR — Inference

### `POST /predict/image`
Phát hiện xe + đọc biển số từ **1 ảnh** upload. Reset tracker state.

**Request:** `multipart/form-data`
```
file: <image file>    # JPEG, PNG, WebP
```

**Response:**
```json
{
  "detections": [
    {
      "track_id": 1,
      "bbox": { "x1": 100, "y1": 80, "x2": 480, "y2": 360 },
      "vehicle_type": "car",
      "license_plate": "MP04CF0655",
      "plate_bbox": { "x1": 160, "y1": 300, "x2": 380, "y2": 340 },
      "confidence": 0.95
    }
  ],
  "processing_time_ms": 45,
  "frame_count": 1
}
```

---

### `POST /predict/frame`
Phát hiện từ 1 frame video (duy trì tracker state giữa các frame). Dùng cho streaming.

**Request:** `multipart/form-data`
```
file: <image file>
```

**Response:** Giống `/predict/image`.

---

### `POST /reset`
Reset tracker state (xóa lịch sử tracking). Gọi khi đổi luồng video.

**Response:**
```json
{ "message": "Tracker reset." }
```

---

## 3. Stream — Camera

### `POST /stream/start`
Bắt đầu capture từ nguồn video.

**Request:**
```json
{
  "source": "0",
  "mode": "lpr"
}
```

| Field | Giá trị | Mô tả |
|-------|---------|-------|
| `source` | `"0"`, `"1"` | Webcam theo index |
| `source` | `"rtsp://..."` | RTSP stream |
| `source` | `"http://192.168.1.50:81/stream"` | ESP32-S3 MJPEG |
| `source` | `"path/to/video.mp4"` | File video |
| `mode` | `"lpr"` | Full pipeline: detect + track + OCR |
| `mode` | `"detect"` | Chỉ detect (nhanh hơn) |

**Response:**
```json
{ "message": "Stream started.", "source": "0", "mode": "lpr" }
```

---

### `POST /stream/stop`
Dừng stream hiện tại.

**Response:**
```json
{ "message": "Stream stopped." }
```

---

### `GET /stream/status`
Trạng thái stream hiện tại.

**Response:**
```json
{
  "active": true,
  "source": "0",
  "mode": "lpr",
  "fps": 24.7,
  "frame_count": 1250,
  "resolution": { "width": 640, "height": 480 }
}
```

---

### `GET /stream/feed`
**MJPEG live stream** — nhúng trực tiếp vào `<img>` tag.

```html
<img src="http://localhost:8000/stream/feed" />
```

**Content-Type:** `multipart/x-mixed-replace; boundary=frame`  
> Frame được annotate với bbox, track ID, biển số.

---

## 4. Evidence — Violation Images

> Thiết kế self-contained: **1 API call = đủ hết thông tin**.  
> Không cần gọi thêm bất kỳ endpoint nào khác.

### `GET /evidence/violations`
Danh sách vi phạm dạng feed với thumbnail (web + mobile).

**Query params:**
| Param | Type | Default | Mô tả |
|-------|------|---------|-------|
| `camera_id` | int | – | Lọc theo camera |
| `license_plate` | string | – | Tìm biển số (partial match) |
| `violation_type` | string | – | `red_light` / `wrong_lane` / `speeding` |
| `limit` | int | 20 | Mobile: 20, Web: 50 |
| `offset` | int | 0 | Pagination |

**Response:**
```json
{
  "items": [
    {
      "id": 42,
      "timestamp": "2026-04-08T14:30:00Z",
      "timestamp_vn": "2026-04-08 21:30:00",
      "violation_type": "red_light",
      "traffic_light_state": "red",
      "license_plate": "MP04CF0655",
      "confidence": 0.95,
      "thumbnail_url": "https://xxx.supabase.co/.../vehicle/...webp",
      "camera_id": 1,
      "camera_name": "Cam Ngã Tư 1",
      "camera_location": "Ngã tư Hàng Xanh"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

> `thumbnail_url` = ảnh vehicle crop (có bbox đỏ) — dùng để hiển thị card.

---

### `GET /evidence/violations/{id}`
**Chi tiết đầy đủ 1 vi phạm + 3 ảnh bằng chứng.**

**Response:**
```json
{
  "id": 42,
  "timestamp": "2026-04-08T14:30:00Z",
  "timestamp_vn": "2026-04-08 21:30:00",
  "violation_type": "red_light",
  "traffic_light_state": "red",

  "camera": {
    "id": 1,
    "name": "Cam Ngã Tư 1",
    "location": "Ngã tư Hàng Xanh"
  },

  "vehicle": {
    "type": "car",
    "track_id": 7,
    "bbox": {
      "x1": 120, "y1": 80, "x2": 480, "y2": 360,
      "width": 360, "height": 280
    }
  },

  "plate": {
    "text": "MP04CF0655",
    "confidence": 0.95,
    "vote_count": 12,
    "vote_percent": 91.7
  },

  "images": {
    "original": {
      "url": "https://xxx.supabase.co/storage/v1/object/public/violations/original/..._t7.webp",
      "format": "webp"
    },
    "vehicle": {
      "url": "https://xxx.supabase.co/storage/v1/object/public/violations/vehicle/..._t7.webp",
      "format": "webp"
    },
    "plate": {
      "url": "https://xxx.supabase.co/storage/v1/object/public/violations/plate/..._t7.webp",
      "format": "webp"
    }
  },

  "processing_time_ms": 45
}
```

**3 loại ảnh:**
| Key | Nội dung | Dùng cho |
|-----|---------|---------|
| `images.original` | Full frame, **không vẽ gì** | Bằng chứng pháp lý |
| `images.vehicle` | Crop xe + **khung đỏ + label biển số** | Hiển thị vi phạm |
| `images.plate` | Biển số **phóng to + viền vàng + text** | Đọc biển số |

---

### `GET /evidence/violations/{id}/image/{type}`
Serve ảnh binary trực tiếp từ API.

**Path params:**
- `type`: `original` | `vehicle` | `plate`

**Behavior:**
- Nếu ảnh trên Supabase → **302 Redirect** về CDN URL
- Nếu ảnh trên local disk → trả binary **image/webp**

**Response headers:**
```
Content-Type: image/webp
Cache-Control: public, max-age=86400
```

---

### `GET /evidence/snapshot/{camera_id}?quality=80`
Live snapshot của camera đang stream — trả WebP.

| Param | Default | Mô tả |
|-------|---------|-------|
| `quality` | 80 | WebP quality 10-100 |

**Response:** Binary `image/webp`  
**Errors:**
- `409` — Stream chưa start
- `503` — Stream đang start nhưng chưa có frame

---

### `GET /evidence/stats`
Thống kê tóm tắt cho dashboard header.

**Response:**
```json
{
  "total_violations": 1520,
  "today": {
    "date": "2026-04-08",
    "count": 47
  },
  "cameras": [
    {
      "id": 1,
      "name": "Cam Ngã Tư 1",
      "location": "Ngã tư Hàng Xanh",
      "total_violations": 800,
      "status": "active"
    }
  ],
  "daily_trend": [
    { "date": "2026-04-08", "count": 47 },
    { "date": "2026-04-07", "count": 52 }
  ]
}
```

---

## 5. Violations — CRUD

### `GET /violations`
Danh sách vi phạm với filter.

**Query params:** `camera_id`, `license_plate`, `limit` (max 500), `offset`

**Response:** Array của raw violation rows từ `view_violations_full`.

---

### `GET /violations/stats/daily`
Thống kê theo ngày từ `view_daily_stats`.

**Query params:** `camera_id` (optional)

**Response:**
```json
[
  {
    "date_vn": "2026-04-08",
    "camera_id": 1,
    "violation_count": 47,
    "unique_plates": 35,
    "avg_confidence": 0.9123,
    "avg_quality": 87.50
  }
]
```

---

### `GET /violations/{id}`
Chi tiết 1 vi phạm (raw từ DB).

---

### `POST /violations`
Ghi violation khi URL ảnh đã biết trước (pre-uploaded).

**Request:**
```json
{
  "camera_id": 1,
  "timestamp": "2026-04-08T14:30:00Z",
  "violation_type": "red_light",
  "traffic_light_state": "red",
  "license_plate": "MP04CF0655",
  "confidence": 0.95,
  "full_image_url": "https://...",
  "cropped_vehicle_url": "https://...",
  "cropped_plate_url": "https://..."
}
```

**Response (201):**
```json
{ "message": "Violation recorded (id=42)." }
```

---

### `POST /violations/with-images`
Upload ảnh raw (JPEG/PNG) → server tự compress WebP → upload storage → ghi DB.

**Request:** `multipart/form-data`

| Field | Required | Mô tả |
|-------|----------|-------|
| `camera_id` | ✓ | Camera ID |
| `timestamp` | ✓ | ISO 8601 UTC |
| `violation_type` | – | Default: `red_light` |
| `traffic_light_state` | – | Default: `red` |
| `license_plate` | – | Biển số |
| `confidence` | – | 0.0-1.0 |
| `track_id` | – | Tracker ID |
| `vehicle_x1/y1/x2/y2` | – | Bbox xe (pixel) |
| `plate_x1/y1/x2/y2` | – | Bbox biển số (pixel) |
| `full_frame` | ✓ | File ảnh gốc |

**Response (201):**
```json
{
  "id": 42,
  "message": "Violation recorded with WebP images.",
  "original_url": "https://xxx.supabase.co/.../original/...webp",
  "vehicle_url": "https://xxx.supabase.co/.../vehicle/...webp",
  "plate_url": "https://xxx.supabase.co/.../plate/...webp"
}
```

---

### `POST /violations/with-images/b64`
Upload ảnh dạng base64 JSON — **nhanh nhất cho internal pipeline**.

**Request:**
```json
{
  "camera_id": 1,
  "timestamp": "2026-04-08T14:30:00Z",
  "violation_type": "red_light",
  "traffic_light_state": "red",
  "license_plate": "MP04CF0655",
  "confidence": 0.95,
  "track_id": 7,
  "vote_count": 12,
  "vote_percent": 91.7,
  "processing_time_ms": 45,
  "full_frame_b64": "<base64 string>",
  "vehicle_bbox": [120, 80, 480, 360],
  "plate_bbox": [160, 300, 380, 340]
}
```

**Response (201):** Giống `/with-images`.

---

### `POST /violations/{id}/ocr`
Thêm kết quả OCR voting cho 1 frame.

**Request:**
```json
{
  "frame_id": 5,
  "track_id": 7,
  "license_plate": "MP04CF0655",
  "confidence": 0.93,
  "quality_score": 85.5
}
```

**Response:**
```json
{ "message": "OCR result added." }
```

---

### `GET /violations/snapshot/webp`
Frame hiện tại dạng WebP.

**Query:** `quality` (10-100, default 80)  
**Response:** Binary `image/webp`

---

## 6. Cameras — CRUD

### `GET /cameras`
Danh sách tất cả camera từ `view_camera_summary`.

**Response:**
```json
[
  {
    "camera_id": 1,
    "camera_name": "Cam Ngã Tư 1",
    "location": "Ngã tư Hàng Xanh",
    "status": "active",
    "online": true,
    "violations_today": 12,
    "violations_total": 800,
    "stream_url": "http://192.168.1.50:81/stream",
    "ip_address": "192.168.1.50",
    "fw_version": "1.2.3",
    "last_seen_at": "2026-04-08T14:55:00Z"
  }
]
```

---

### `GET /cameras/{id}`
Chi tiết 1 camera + provisioning.

---

### `POST /cameras`
Tạo camera mới.

**Request:**
```json
{
  "camera_id": 2,
  "camera_name": "Cam Ngã Tư 2",
  "location": "Ngã tư Đinh Tiên Hoàng",
  "latitude": 10.7890,
  "longitude": 106.6940,
  "status": "inactive"
}
```

---

### `PUT /cameras/{id}`
Cập nhật thông tin camera.

---

### `DELETE /cameras/{id}`
Xóa camera (cascade xóa zones, violations liên quan).

---

### `PUT /cameras/{id}/provisioning`
ESP32-S3 tự đăng ký khi boot. Cũng dùng để sync từ ThingsBoard.

**Request:**
```json
{
  "device_name": "cam-junction-01",
  "ip_address": "192.168.1.50",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "fw_version": "1.2.3",
  "wifi_ssid": "TrafficNet",
  "resolution": "640x480",
  "stream_scheme": "http",
  "stream_host": "192.168.1.50",
  "stream_port": 81,
  "stream_path": "/stream",
  "online": true,
  "last_seen_at": "2026-04-08T14:30:00Z"
}
```

---

## 7. Detection Zones

### `GET /zones?camera_id=1`
Lấy tất cả zone, lọc theo camera.

**Response:**
```json
[
  {
    "id": "uuid-here",
    "camera_id": 1,
    "zone_name": "zone-1",
    "x": 120, "y": 80,
    "width": 400, "height": 280,
    "zone_type": "detection",
    "active": true
  }
]
```

---

### `POST /zones`
Tạo zone mới.

**Request:**
```json
{
  "camera_id": 1,
  "zone_name": "stop-line",
  "x": 0, "y": 250,
  "width": 640, "height": 10,
  "zone_type": "stop_line",
  "active": true
}
```

---

### `PUT /zones/{id}`
Cập nhật zone.

---

### `DELETE /zones/{id}`
Xóa zone.

---

## 8. MQTT — IoT Control

### `GET /mqtt/status`
Trạng thái MQTT broker connection.

**Response:**
```json
{
  "connected": true,
  "broker": "192.168.1.8:1888",
  "client_id": "trafficcam-backend"
}
```

---

### `POST /mqtt/traffic-light/{device_name}/mode`
Gửi lệnh mode cho đèn giao thông PCB.

**Path:** `device_name` = tên PCB, VD: `pcb-tl-01`  
**MQTT topic:** `KAI/pcb/pcb-tl-01/cmd`

**Request:**
```json
{ "mode": "emergency_red" }
```

| mode | Lệnh gửi | Ý nghĩa |
|------|---------|---------|
| `normal` | `setNormalMode` | Chạy lại bình thường |
| `emergency_red` | `setEmergencyRed` | Đèn đỏ toàn bộ |
| `emergency_green` | `setEmergencyGreen` | Đèn xanh toàn bộ |
| `start` | `startTraffic` | Bắt đầu chu kỳ đèn |
| `stop` | `stopTraffic` | Dừng chu kỳ đèn |

---

### `POST /mqtt/traffic-light/{device_name}/timings`
Cập nhật thời gian đèn cho PCB.

**Request:**
```json
{
  "red_ms": 25000,
  "yellow_ms": 2000,
  "green_ms": 10000
}
```

**MQTT payload gửi đi:**
```json
{
  "method": "setTimings",
  "params": { "red": 25000, "yellow": 2000, "green": 10000 }
}
```

---

### `POST /mqtt/camera/{device_name}/command`
Gửi lệnh tới ESP32-S3 camera.

**MQTT topic:** `KAI/cameras/{device_name}/cmd`

---

## 9. Local Settings

> Quản lý `data/app_settings.json` — load khi khởi động, không cần DB.

### `GET /local-settings`
Toàn bộ settings JSON.

### `GET /local-settings/{section}`
Một section, VD: `/local-settings/alpr`, `/local-settings/mqtt`.

### `PUT /local-settings/{section}`
Cập nhật section (merge, không overwrite toàn bộ).

**Request:**
```json
{ "data": { "vconf": 0.7, "pconf": 0.3 } }
```

### `POST /local-settings/reload`
Hot-reload từ disk (không restart server).

**Response:**
```json
{ "message": "Settings reloaded from disk." }
```

### `PUT /local-settings/app/enabled`
Bật/tắt app.
```json
{ "enabled": false }
```

### `PUT /local-settings/alpr`
Cập nhật ALPR thresholds.
```json
{
  "vconf": 0.7,
  "pconf": 0.3,
  "ocr_thres": 0.9,
  "read_plate": true,
  "device": "0"
}
```

### `PUT /local-settings/traffic-light/default-timings`
```json
{ "red_ms": 30000, "yellow_ms": 3000, "green_ms": 15000 }
```

### `PUT /local-settings/traffic-light/pcb/{device_name}/timings`
Timing cho từng PCB, lưu local.
```json
{ "red_ms": 25000, "yellow_ms": 2000, "green_ms": 10000 }
```

### `GET /local-settings/cameras/{camera_id}`
Config local của camera (zone, timing, stream URL).

### `PUT /local-settings/cameras/{camera_id}/zones`
Cập nhật zones local.
```json
{
  "data": {
    "detect_zone": [[0.1, 0.4], [0.9, 0.4], [0.9, 0.95], [0.1, 0.95]],
    "stop_line": [[0.1, 0.72], [0.88, 0.64]]
  }
}
```

---

## 10. System Settings (DB)

### `GET /settings`
Tất cả system settings từ DB.

### `GET /settings/{key}`
Lấy 1 setting.

**Response:**
```json
{
  "key": "data_retention",
  "value": { "days": 30 },
  "description": "Violation record retention policy"
}
```

### `PUT /settings/{key}`
Tạo hoặc cập nhật setting.

**Request:**
```json
{
  "value": { "days": 60 },
  "description": "Giữ dữ liệu 60 ngày"
}
```

---

## HTTP Status Codes

| Code | Ý nghĩa |
|------|---------|
| `200` | OK |
| `201` | Tạo mới thành công |
| `302` | Redirect (dùng cho image proxy → CDN) |
| `400` | Request sai (thiếu field, decode lỗi, ...) |
| `404` | Không tìm thấy resource |
| `409` | Conflict (VD: stream chưa active) |
| `500` | Lỗi server (encode WebP fail, ...) |
| `503` | Service not ready (DB chưa connect, model chưa load) |

---

## Error Response Format

```json
{
  "detail": "Violation 999 not found."
}
```

---

## Quick Integration

### Web (JavaScript)
```js
const BASE = 'http://localhost:8000';

// Feed vi phạm
const { items } = await fetch(`${BASE}/evidence/violations?limit=20`).then(r => r.json());

// Chi tiết + ảnh
const ev = await fetch(`${BASE}/evidence/violations/42`).then(r => r.json());
originalImg.src = ev.images.original.url;
vehicleImg.src  = ev.images.vehicle.url;
plateImg.src    = ev.images.plate.url;

// Livestream MJPEG
videoEl.src = `${BASE}/stream/feed`;
```

### Mobile (Flutter)
```dart
final res = await http.get(Uri.parse('$base/evidence/violations/$id'));
final ev = jsonDecode(res.body);
// ev['images']['plate']['url'] → URL ảnh biển số
// ev['plate']['text'] → "MP04CF0655"
```

### Python pipeline (ghi violation)
```python
import httpx, base64, cv2

frame_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
b64 = base64.b64encode(frame_bytes).decode()

resp = httpx.post(f'{BASE}/violations/with-images/b64', json={
    "camera_id": 1,
    "timestamp": "2026-04-08T14:30:00Z",
    "full_frame_b64": b64,
    "vehicle_bbox": [x1, y1, x2, y2],
    "plate_bbox": [px1, py1, px2, py2],
    "license_plate": "MP04CF0655",
    "confidence": 0.95,
    "track_id": 7,
})
data = resp.json()
print(data["plate_url"])  # URL ảnh biển số
```
