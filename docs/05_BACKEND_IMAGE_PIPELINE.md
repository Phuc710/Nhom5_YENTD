# Pipeline xử lý ảnh backend

Tài liệu này mô tả pipeline xử lý ảnh hiện tại của backend và hướng cần chuẩn hóa tiếp theo.

## 1. Pipeline hiện tại trong code

Luồng đang chạy:

```text
ESP32 gửi 1 frame
-> backend decode ảnh
-> chấm điểm chất lượng
-> lưu ảnh gốc
-> chạy detector
-> đưa vào frame buffer
-> khi đủ điều kiện thì finalize
```

## 2. Các bước đang có thật trong code

### Bước 1: nhận ảnh

Endpoint:

- `POST /api/upload`

Input:

- `file`
- `camera_id`
- `traffic_light_state`
- `timestamp`
- `emergency`

### Bước 2: decode ảnh

Backend dùng `cv2.imdecode(...)` để chuyển bytes JPEG thành ảnh OpenCV.

### Bước 3: chấm điểm chất lượng

Backend gọi `calculate_quality_score(image)`.

Rule hiện tại:

- ảnh có `overall_score < 70` thì bị bỏ qua

### Bước 4: lưu ảnh gốc

Backend lưu ảnh vào:

- `/uploads/original`

### Bước 5: detect biển số

Backend gọi `ml.detector.get_detector().process_image(image_path)`.

### Bước 6: đưa vào buffer

Mỗi frame sau detect được đưa vào `frame_buffer`.

Buffer dùng để:

- gom nhiều frame
- chờ đủ dữ liệu cho tracking và voting

### Bước 7: finalize

Finalize xảy ra khi:

- đủ số frame tối thiểu
- hoặc timeout
- hoặc `emergency=true`

## 3. Những thành phần xử lý chính

- `backend/api/upload.py`
- `backend/services/quality_service.py`
- `backend/services/image_service.py`
- `backend/services/buffer_service.py`
- `backend/services/finalize_service.py`
- `backend/services/voting_service.py`
- `backend/services/tracking_service.py`

## 4. Điểm mạnh của pipeline hiện tại

- đã có quality gate
- đã có buffer nhiều frame
- đã có tracking
- đã có OCR voting
- đã có finalize tách riêng

## 5. Điểm còn thiếu

- chưa dùng `detection_zones` trong quyết định vi phạm
- chưa có bước xác nhận xe đã đi vào vùng vi phạm
- chưa có pipeline detect-only riêng cho test model
- response kỹ thuật cho test camera còn đang trộn với API nghiệp vụ

## 6. Pipeline mục tiêu sau refactor

```text
frame
-> decode
-> quality score
-> detect object / plate
-> map detection vào zone
-> tracking theo track_id
-> OCR
-> voting
-> rule engine xác nhận vi phạm
-> save violation
```

## 7. Tách hai pipeline rõ ràng

### Pipeline nghiệp vụ `v1`

Dùng để:

- nhận frame thật từ ESP32
- gom dữ liệu
- tạo violation chính thức

### Pipeline test `v2-test`

Dùng để:

- test camera
- test model detect
- test OCR
- không ghi DB nghiệp vụ
