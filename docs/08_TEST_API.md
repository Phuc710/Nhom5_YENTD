# Hướng Dẫn Test API

## Truy Cập API Documentation

Backend FastAPI tự động tạo 2 loại docs:

### 1. Swagger UI (Giao diện test tương tác)

```
http://YOUR_VPS_IP:8000/docs
```

**Tính năng**:
- ✅ Test API trực tiếp trên browser
- ✅ Xem request/response examples
- ✅ "Try it out" - gửi request thử nghiệm
- ✅ Schema validation tự động

**Cách sử dụng**:
1. Mở `/docs` trên browser
2. Click vào endpoint muốn test (ví dụ: `POST /api/upload`)
3. Click nút **"Try it out"**
4. Nhập parameters (file, camera_id, traffic_light_state)
5. Click **"Execute"**
6. Xem response ở phía dưới

### 2. ReDoc (Documentation đẹp)

```
http://YOUR_VPS_IP:8000/redoc
```

**Tính năng**:
- ✅ Docs đẹp, dễ đọc
- ✅ Có search
- ✅ Code examples cho nhiều ngôn ngữ
- ✅ Responsive mobile

## Test Upload Endpoint

### Trên Swagger UI

**Bước 1**: Mở `http://localhost:8000/docs`

**Bước 2**: Tìm endpoint `POST /api/upload`

**Bước 3**: Click "Try it out"

**Bước 4**: Điền thông tin:
- `file`: Click "Choose File" → chọn ảnh JPG
- `camera_id`: 1
- `traffic_light_state`: red

**Bước 5**: Click "Execute"

**Bước 6**: Xem response:
```json
{
  "success": true,
  "message": "Processed 1 violation(s)",
  "camera_id": 1,
  "violations": [
    {
      "violation_id": 123,
      "license_plate": "51A-12345",
      "confidence": 0.87
    }
  ]
}
```

### Dùng cURL (Command Line)

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@test_image.jpg" \
  -F "camera_id=1" \
  -F "traffic_light_state=red"
```

### Dùng Python

```python
import requests

url = "http://localhost:8000/api/upload"

# Mở file ảnh
files = {"file": open("test.jpg", "rb")}

# Form data
data = {
    "camera_id": 1,
    "traffic_light_state": "red"
}

# Gửi POST request
response = requests.post(url, files=files, data=data)

# In kết quả
print(response.json())
```

### Dùng Postman

1. Tạo request mới: `POST http://localhost:8000/api/upload`
2. Chọn tab **Body** → **form-data**
3. Thêm fields:
   - `file` (type: File) → chọn ảnh
   - `camera_id` (type: Text) → nhập `1`
   - `traffic_light_state` (type: Text) → nhập `red`
4. Click **Send**

## Test Các Endpoints Khác

### Lấy Danh Sách Vi Phạm

```bash
# Tất cả vi phạm
curl http://localhost:8000/api/violations

# Vi phạm hôm nay
curl http://localhost:8000/api/violations?period=today

# Vi phạm từ camera 1
curl http://localhost:8000/api/violations?camera_id=1

# Tìm theo biển số
curl "http://localhost:8000/api/violations?license_plate=51A"

# Kết hợp filters
curl "http://localhost:8000/api/violations?period=week&camera_id=1&limit=10"
```

### Lấy Chi Tiết Vi Phạm

```bash
curl http://localhost:8000/api/violations/123
```

### Xóa Vi Phạm

```bash
curl -X DELETE http://localhost:8000/api/violations/123
```

### Lấy Thống Kê

```bash
# Thống kê tổng quan
curl http://localhost:8000/api/stats

# Thống kê theo camera
curl http://localhost:8000/api/stats/by-camera

# Thống kê theo giờ (7 ngày qua)
curl http://localhost:8000/api/stats/by-hour?days=7
```

### Lấy Danh Sách Camera

```bash
curl http://localhost:8000/api/cameras
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Ví Dụ Response

### Upload Thành Công

```json
{
  "success": true,
  "message": "Processed 1 violation(s)",
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

### Không Phát Hiện Biển Số

```json
{
  "success": true,
  "message": "No license plates detected",
  "camera_id": 1,
  "image_url": "/uploads/original/cam1_xxx.jpg"
}
```

### Không Phải Đèn Đỏ

```json
{
  "success": true,
  "message": "Image received but not red light - skipped processing",
  "camera_id": 1,
  "traffic_light_state": "green"
}
```

### Danh Sách Vi Phạm

```json
{
  "success": true,
  "data": [
    {
      "id": 123,
      "camera_id": 1,
      "image_url": "/uploads/original/cam1_xxx.jpg",
      "plate_image_url": "/uploads/detected_plates/plate_xxx.jpg",
      "license_plate": "51A-12345",
      "confidence": 0.87,
      "traffic_light_state": "red",
      "timestamp": "2026-01-27T22:05:30",
      "created_at": "2026-01-27T22:05:35"
    }
  ],
  "count": 1,
  "limit": 50,
  "offset": 0
}
```

### Thống Kê

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

## Test Với Ảnh Mẫu

### Tạo Ảnh Test

Bạn cần ảnh có:
- Xe ô tô/xe máy
- Biển số rõ ràng
- Đủ sáng
- Format: JPG
- Kích thước: tối thiểu 640x480

### Download Ảnh Mẫu

```bash
# Tải ảnh test từ internet
wget https://example.com/car-with-plate.jpg -O test.jpg
```

### Test Upload

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@test.jpg" \
  -F "camera_id=1" \
  -F "traffic_light_state=red"
```

## Xem Ảnh Đã Upload

Sau khi upload thành công, ảnh được lưu tại:

- **Ảnh gốc**: `http://localhost:8000/uploads/original/cam1_xxx.jpg`
- **Ảnh biển số**: `http://localhost:8000/uploads/detected_plates/plate_xxx.jpg`

Mở URL trong browser để xem.

## Lỗi Thường Gặp

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

**Nguyên nhân**: Thiếu field bắt buộc

**Giải pháp**: Kiểm tra lại tất cả fields: `file`, `camera_id`, `traffic_light_state`

### 500 Internal Server Error

```json
{
  "detail": "Cannot read image: /path/to/image.jpg"
}
```

**Nguyên nhân**: Lỗi xử lý ảnh

**Giải pháp**:
- Kiểm tra file ảnh hợp lệ
- Kiểm tra YOLO models đã có trong `backend/ml/`
- Xem logs server: `journalctl -u traffic-backend -f`

### Connection Refused

```
curl: (7) Failed to connect to localhost port 8000: Connection refused
```

**Nguyên nhân**: Backend chưa chạy

**Giải pháp**:
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Tips & Tricks

### 1. Xem Request/Response Headers

```bash
curl -v http://localhost:8000/api/violations
```

### 2. Pretty Print JSON

```bash
curl http://localhost:8000/api/stats | python -m json.tool
```

### 3. Save Response to File

```bash
curl http://localhost:8000/api/violations > violations.json
```

### 4. Test với nhiều ảnh

```bash
for img in *.jpg; do
  echo "Testing $img..."
  curl -X POST http://localhost:8000/api/upload \
    -F "file=@$img" \
    -F "camera_id=1" \
    -F "traffic_light_state=red"
  echo ""
done
```

### 5. Benchmark Performance

```bash
# Cài Apache Bench
sudo apt install apache2-utils

# Test 100 requests
ab -n 100 -c 10 http://localhost:8000/api/violations
```

## Tự Động Hóa Testing

### Python Script

```python
import requests
import glob

url = "http://localhost:8000/api/upload"

# Test tất cả ảnh trong folder
for img_path in glob.glob("test_images/*.jpg"):
    print(f"Testing {img_path}...")
    
    files = {"file": open(img_path, "rb")}
    data = {"camera_id": 1, "traffic_light_state": "red"}
    
    response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success: {result['message']}")
    else:
        print(f"❌ Failed: {response.status_code}")
```

## Kết Luận

- Swagger UI (`/docs`) là cách nhanh nhất để test
- cURL tốt cho automation
- Python requests tốt cho integration testing
- Luôn kiểm tra response status code và message
