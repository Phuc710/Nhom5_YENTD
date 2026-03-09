# Tổng quan backend

## 1. Mô hình triển khai

```text
ESP32-S3-DevKitC-1
- camera
- 1 đèn giao thông
- 2 nút vật lý (đỏ, xanh)
        |
        | MQTT telemetry / RPC
        v
ThingsBoard + Mosquitto trên laptop
        |
        | HTTP stream / upload frame / provisioning sync
        v
Backend FastAPI trên laptop hoặc PC
        |
        | đọc / ghi dữ liệu
        v
Supabase PostgreSQL
        ^
        |
Frontend PHP/JS trên hosting
```

## 2. Vai trò backend

Backend là lớp trung tâm xử lý nghiệp vụ. Backend chịu trách nhiệm:

- nhận frame từ ESP32
- nhận heartbeat từ ESP32 khi không ở pha đỏ
- đánh giá chất lượng ảnh
- detect biển số
- tracking object theo nhiều frame
- OCR và voting
- tạo vi phạm
- quản lý camera, zone, thống kê
- gom dữ liệu riêng cho dashboard cảnh sát
- đồng bộ dữ liệu với Supabase
- cung cấp API duy nhất cho frontend

## 3. Logic đèn giao thông

### Chế độ bình thường

- Chu kỳ `đỏ -> xanh -> vàng -> đỏ`
- Có thời gian cho từng pha
- Thời gian có thể đổi từ ThingsBoard

### Chế độ khẩn cấp đỏ

- Nút đỏ hoặc RPC `setEmergencyRed`
- Khóa đèn ở trạng thái đỏ
- Dừng chu kỳ
- Dừng đếm thời gian
- Nhấn lại nút đỏ hoặc gọi `setNormalMode` để quay về bình thường

### Chế độ khẩn cấp xanh

- Nút xanh hoặc RPC `setEmergencyGreen`
- Khóa đèn ở trạng thái xanh
- Dừng chu kỳ
- Dừng đếm thời gian
- Nhấn lại nút xanh hoặc gọi `setNormalMode` để quay về bình thường

## 4. Luồng nghiệp vụ mục tiêu

### Luồng A: camera và provisioning

1. ESP32 khởi động.
2. Kết nối WiFi.
3. Provision lên ThingsBoard nếu chưa có token.
4. MQTT kết nối ThingsBoard.
5. Firmware tự gọi `POST /api/cameras/provision`.
6. Backend cập nhật `cameras` và `camera_provisioning`.
7. Frontend lấy dữ liệu camera qua API để hiển thị.

### Luồng B: stream trực tiếp

1. ESP32 có IP nội bộ và phát stream tại `/stream`.
2. Firmware sync `ip_address` về backend.
3. Backend tự cập nhật `stream_url = http://<ip>/stream` nếu camera đang dùng URL tự sinh.
3. Frontend gọi `GET /api/cameras/{camera_id}`.
4. Trang camera hiển thị stream thời gian thực.

### Luồng C: cấu hình zone

1. Admin mở trang camera.
2. Vẽ `detection`, `stop_line`, `roi`.
3. Frontend gọi `PUT /api/cameras/{camera_id}/zones`.
4. Backend lưu dữ liệu vào `detection_zones`.

### Luồng D: phát hiện vượt đèn đỏ

1. Đèn đang ở trạng thái đỏ.
2. ESP32 chỉ upload frame khi đèn đang đỏ hoặc `emergency_red`.
3. Xe đi vào vùng vi phạm đã cấu hình.
4. Backend nhận `traffic_light_state`, `operation_mode`, `tl_state_ms`.
5. Backend detect, tracking, OCR và vote.
6. Khi đèn chuyển `đỏ -> xanh`, ESP32 gọi `POST /api/finalize`.
7. Backend đối chiếu với `detection_zones`.
8. Nếu đúng điều kiện vi phạm:
   - chọn frame tốt nhất
   - lưu ảnh gốc
   - crop biển số
   - tạo bản ghi `violations`
   - lưu lịch sử OCR nếu cần

### Luồng E: emergency mode

- `emergency_red`: có thể vẫn ghi nhận vi phạm nếu xe vào vùng cấm khi đèn đang bị khóa đỏ.
- `emergency_green`: không nên tạo vi phạm red-light.
- `green` hoặc `yellow`: firmware không upload full frame lên backend, chỉ heartbeat để giữ trạng thái online.

## 5. Thành phần code backend hiện có

- `backend/main.py`
- `backend/api`
- `backend/services`
- `backend/repositories`
- `backend/models`
- `backend/database`
- `backend/ml`

## 5.1. Tài liệu ThingsBoard liên quan

Chi tiết riêng cho `ThingsBoard + Provisioning + MQTT + OTA` xem tại:

- [`thingsboard/00_README.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/00_README.md)
- [`thingsboard/01_ARCHITECTURE_AND_MATCHING.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/01_ARCHITECTURE_AND_MATCHING.md)
- [`thingsboard/02_PROVISIONING_AND_IDENTITY.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/02_PROVISIONING_AND_IDENTITY.md)
- [`thingsboard/03_MQTT_ATTRIBUTES_RPC.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
- [`thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md)
- [`thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md)
- [`thingsboard/06_STANDARD_OPERATION_FLOWS.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/06_STANDARD_OPERATION_FLOWS.md)

## 6. Các khoảng cách giữa code và logic mục tiêu

Đã có:

- upload frame
- heartbeat
- finalize
- CRUD camera
- lưu zone
- thống kê
- tracking và voting OCR
- namespace dashboard riêng cho web cảnh sát
- firmware tự sync provisioning về backend
- backend tự cập nhật `stream_url` từ IP nội bộ

Chưa có đầy đủ:

- rule `xe đi vào zone khi đèn đỏ là vi phạm`
- rule cắt `stop_line`
- bridge trạng thái đèn hiện thời từ ThingsBoard về backend/frontend
- chuẩn hóa response schema toàn bộ API `v1`
