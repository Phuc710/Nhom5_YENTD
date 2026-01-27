# Tài Liệu API

## Tổng Quan

Backend FastAPI cung cấp REST API để:
- Upload ảnh từ ESP32-CAM
- Quản lý vi phạm
- Quản lý camera
- Thống kê

**Base URL**: `http://YOUR_VPS_IP:8000`

**API Docs**: 
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Authentication

Hiện tại: **Không có authentication** (demo)

Production cần thêm:
- JWT tokens
- API keys cho ESP32
- Role-based access control

## Endpoints

### 1. Upload Ảnh

**POST** `/api/upload`

Upload ảnh từ ESP32-CAM để phát hiện vi phạm.

**Request**:
```http
POST /api/upload
Content-Type: multipart/form-data

file: [binary image data]
camera_id: 1
traffic_light_state: red
```

**Response Success**:
```json
{
  "success": true,
  "message": "Xử lý 1 vi phạm",
  "camera_id": 1,
  "violations": [
    {
      "violation_id": 123,
      "license_plate": "51A-12345",
      "confidence": 0.87
    }
  ],
  "timestamp": "2026-01-27T22:05:30"
}
```

**Response - Không Detect**:
```json
{
  "success": true,
  "message": "Không phát hiện biển số - không lưu ảnh",
  "camera_id": 1,
  "detected_count": 0
}
```

**Response - Không Phải Đèn Đỏ**:
```json
{
  "success": true,
  "message": "Ảnh nhận được nhưng không phải đèn đỏ - bỏ qua",
  "camera_id": 1,
  "traffic_light_state": "green"
}
```

**cURL Example**:
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@image.jpg" \
  -F "camera_id=1" \
  -F "traffic_light_state=red"
```

---

### 2. Lấy Danh Sách Vi Phạm

**GET** `/api/violations`

Lấy danh sách vi phạm với filter.

**Query Parameters**:

| Parameter | Type | Default | Mô tả |
|-----------|------|---------|-------|
| `period` | String | - | `today`, `week`, `month` |
| `camera_id` | Integer | - | Filter theo camera |
| `license_plate` | String | - | Tìm kiếm biển số (partial match) |
| `limit` | Integer | 50 | Số lượng kết quả |
| `offset` | Integer | 0 | Offset cho pagination |

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "id": 123,
      "camera_id": 1,
      "image_url": "/uploads/original/cam1_20260127_220530_abc123.jpg",
      "plate_image_url": "/uploads/detected_plates/plate_abc123.jpg",
      "license_plate": "51A-12345",
      "confidence": 0.87,
      "traffic_light_state": "red",
      "violation_type": "red_light_violation",
      "timestamp": "2026-01-27T22:05:30",
      "created_at": "2026-01-27T22:05:35"
    }
  ],
  "count": 1,
  "limit": 50,
  "offset": 0
}
```

**Examples**:

```bash
# Tất cả vi phạm
curl http://localhost:8000/api/violations

# Vi phạm hôm nay
curl http://localhost:8000/api/violations?period=today

# Vi phạm từ camera 1
curl http://localhost:8000/api/violations?camera_id=1

# Tìm biển số
curl "http://localhost:8000/api/violations?license_plate=51A"

# Kết hợp filters
curl "http://localhost:8000/api/violations?period=week&camera_id=1&limit=10"
```

---

### 3. Lấy Chi Tiết Vi Phạm

**GET** `/api/violations/{id}`

Lấy thông tin chi tiết 1 vi phạm.

**Response**:
```json
{
  "success": true,
  "data": {
    "id": 123,
    "camera_id": 1,
    "image_url": "/uploads/original/cam1_20260127_220530_abc123.jpg",
    "plate_image_url": "/uploads/detected_plates/plate_abc123.jpg",
    "license_plate": "51A-12345",
    "confidence": 0.87,
    "traffic_light_state": "red",
    "violation_type": "red_light_violation",
    "timestamp": "2026-01-27T22:05:30",
    "created_at": "2026-01-27T22:05:35"
  }
}
```

**Example**:
```bash
curl http://localhost:8000/api/violations/123
```

---

### 4. Xóa Vi Phạm

**DELETE** `/api/violations/{id}`

Xóa 1 vi phạm.

**Response**:
```json
{
  "success": true,
  "message": "Đã xóa vi phạm"
}
```

**Example**:
```bash
curl -X DELETE http://localhost:8000/api/violations/123
```

---

### 5. Lấy Danh Sách Camera

**GET** `/api/cameras`

Lấy tất cả camera.

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "camera_id": 1,
      "camera_name": "Camera Gò Vấp",
      "location": "Ngã tư Phan Văn Trị - Quang Trung",
      "latitude": 10.8231,
      "longitude": 106.6297,
      "status": "active"
    }
  ],
  "count": 3
}
```

---

### 6. Thống Kê Tổng Quan

**GET** `/api/stats`

Lấy thống kê tổng quan.

**Response**:
```json
{
  "success": true,
  "data": {
    "total_violations": 1523,
    "today_violations": 45,
    "week_violations": 312,
    "month_violations": 987
  },
  "timestamp": "2026-01-27T22:05:30"
}
```

---

### 7. Thống Kê Theo Camera

**GET** `/api/stats/by-camera`

Thống kê vi phạm theo từng camera.

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "camera_id": 1,
      "camera_name": "Camera Gò Vấp",
      "violation_count": 523
    },
    {
      "camera_id": 2,
      "camera_name": "Camera Củ Chi",
      "violation_count": 412
    }
  ]
}
```

---

### 8. Thống Kê Theo Giờ

**GET** `/api/stats/by-hour`

Thống kê vi phạm theo giờ trong ngày.

**Query Parameters**:
- `days`: Số ngày lấy dữ liệu (default: 7)

**Response**:
```json
{
  "success": true,
  "data": [
    {"hour": 0, "count": 12},
    {"hour": 1, "count": 8},
    {"hour": 7, "count": 45},
    {"hour": 8, "count": 67},
    {"hour": 17, "count": 89},
    {"hour": 18, "count": 102}
  ]
}
```

---

### 9. Health Check

**GET** `/health`

Kiểm tra server status.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-27T22:05:30.123456"
}
```

---

### 10. Root

**GET** `/`

API info.

**Response**:
```json
{
  "message": "API Phát Hiện Vi Phạm Giao Thông",
  "status": "online",
  "docs": "/docs",
  "timestamp": "2026-01-27T22:05:30.123456"
}
```

## Error Responses

### 400 Bad Request

```json
{
  "detail": "Không thể đọc ảnh"
}
```

### 404 Not Found

```json
{
  "detail": "Không tìm thấy vi phạm"
}
```

### 422 Unprocessable Entity

```json
{
  "detail": [
    {
      "loc": ["body", "camera_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error"
}
```

## Data Models

### Violation

```typescript
interface Violation {
  id: number;
  camera_id: number;
  image_url: string;
  plate_image_url: string | null;
  license_plate: string;
  confidence: number;  // 0.0 - 1.0
  traffic_light_state: "red" | "yellow" | "green";
  violation_type: string;
  timestamp: string;  // ISO 8601
  created_at: string;
}
```

### Camera

```typescript
interface Camera {
  id: number;
  camera_id: number;
  camera_name: string;
  location: string;
  latitude: number;
  longitude: number;
  status: "active" | "inactive";
}
```

### Stats

```typescript
interface Stats {
  total_violations: number;
  today_violations: number;
  week_violations: number;
  month_violations: number;
}
```

## Rate Limiting

Hiện tại: **Không có rate limiting**

Production khuyến nghị:
- 100 requests/minute cho upload
- 1000 requests/minute cho read endpoints

## CORS

Hiện tại: **Allow all origins** (`*`)

Production: Chỉ cho phép domain cụ thể:
```python
allow_origins=["https://your-domain.com"]
```

## Pagination

Endpoints hỗ trợ pagination:
- `/api/violations`

Parameters:
- `limit`: Số lượng kết quả (default: 50, max: 100)
- `offset`: Bỏ qua N kết quả đầu

Example:
```bash
# Page 1 (0-49)
curl "http://localhost:8000/api/violations?limit=50&offset=0"

# Page 2 (50-99)
curl "http://localhost:8000/api/violations?limit=50&offset=50"
```

## Filtering

### Period Filter

- `today`: Hôm nay (00:00 - 23:59)
- `week`: 7 ngày qua
- `month`: 30 ngày qua

### License Plate Search

Partial match, case-insensitive:
```bash
# Tìm tất cả biển số chứa "51A"
curl "http://localhost:8000/api/violations?license_plate=51A"
```

## Image URLs

Tất cả image URLs là relative paths:

```
/uploads/original/cam1_20260127_220530_abc123.jpg
/uploads/detected_plates/plate_abc123.jpg
```

Full URL:
```
http://YOUR_VPS_IP:8000/uploads/original/cam1_20260127_220530_abc123.jpg
```

## Testing

### Swagger UI

Mở browser: `http://localhost:8000/docs`

1. Click endpoint
2. Click "Try it out"
3. Nhập parameters
4. Click "Execute"
5. Xem response

### cURL

```bash
# Upload test
curl -X POST http://localhost:8000/api/upload \
  -F "file=@test.jpg" \
  -F "camera_id=1" \
  -F "traffic_light_state=red"

# Get violations
curl http://localhost:8000/api/violations?period=today

# Get stats
curl http://localhost:8000/api/stats
```

### Python

```python
import requests

# Upload
files = {"file": open("test.jpg", "rb")}
data = {"camera_id": 1, "traffic_light_state": "red"}
response = requests.post("http://localhost:8000/api/upload", files=files, data=data)
print(response.json())

# Get violations
response = requests.get("http://localhost:8000/api/violations?period=today")
print(response.json())
```

## Best Practices

1. **Luôn kiểm tra `success` field** trong response
2. **Handle errors** với try-catch
3. **Validate data** trước khi gửi
4. **Dùng HTTPS** trong production
5. **Implement retry logic** cho network errors
6. **Cache responses** khi có thể
7. **Monitor API performance**
