# Tổng Quan Backend

## 1. Kiến trúc hiện tại

```text
ESP32-S3 camera
    -> phát MJPEG stream nội bộ
    -> có thể sync provisioning/identity về backend
    -> có thể được ThingsBoard quản lý ở lớp thiết bị

ThingsBoard
    -> quản lý device identity / attributes / RPC / OTA
    -> là lớp điều phối thiết bị

Backend FastAPI
    -> đồng bộ camera từ ThingsBoard hoặc provisioning
    -> proxy stream / snapshot cho web hosting
    -> quản lý camera / zone / violation / dashboard
    -> chuẩn hóa dữ liệu cho frontend

Supabase PostgreSQL
    -> lưu cameras
    -> lưu camera_provisioning
    -> lưu detection_zones
    -> lưu violations / ocr_results

Frontend PHP/JS
    -> chỉ gọi backend
    -> không gọi trực tiếp ThingsBoard
```

## 2. Vai trò backend

Backend là lớp trung gian chuẩn hóa dữ liệu để web không phụ thuộc vào:

- IP nội bộ đổi liên tục
- tên thiết bị hardcode
- raw JSON của ThingsBoard
- access token hoặc RPC trực tiếp

Backend hiện chịu trách nhiệm:

- CRUD camera và zone
- đồng bộ danh sách device từ ThingsBoard
- khi sync từ ThingsBoard, cố lấy thêm runtime attributes/telemetry mới nhất theo kiểu best-effort
- nhận provisioning sync từ ESP32 nếu có
- chuẩn hóa tên camera hiển thị
- chuẩn hóa `stream_url` và `snapshot`
- proxy MJPEG stream cho hosting
- cung cấp API dashboard
- lưu violation và ảnh nghiệp vụ

## 3. Luồng dữ liệu chuẩn

### Luồng A: đăng ký và đồng bộ camera

1. Device xuất hiện trên ThingsBoard hoặc gọi provisioning sync về backend.
2. Backend upsert `cameras` và `camera_provisioning`.
3. Nếu `camera_id` từ provisioning xung đột với `tb_device_name` hoặc `mac_address` đã map sẵn, backend ưu tiên mapping identity đang có để tránh bind nhầm camera.
4. DB tự chuẩn hóa tên hiển thị bằng thứ tự ưu tiên:
   `camera_name -> tb_device_name -> device_name -> project_name -> Camera 00x`
5. Web đọc `view_camera_summary` và tự có camera mới.

### Luồng B: stream lên web hosting

1. ESP32 phát stream cục bộ.
2. Provisioning lưu `stream_scheme`, `stream_host`, `stream_port`, `stream_path`, `stream_snapshot_path`.
3. Nếu `cameras.stream_url` trống, DB/backend tự dựng `stream_url`.
4. Frontend bấm `Connect`.
5. Web mở qua backend proxy `/api/cameras/{id}/stream`.

### Luồng C: override thủ công

Nếu cần đặc biệt:

- đặt `camera_name` trong bảng `cameras`
- đặt `stream_url` trong bảng `cameras`

Hai giá trị này sẽ được ưu tiên hơn dữ liệu tự sinh từ provisioning.

## 4. Những điểm chuẩn hóa mới

- Không hardcode tên model kiểu `PCB Cam AI S3 001` ở web/backend.
- Không hardcode domain API trong frontend nếu cùng domain.
- Không hardcode `stream_url` từ riêng `ip_address`; giờ có thể dựng từ `scheme + host + port + path`.
- `camera_provisioning.extra_attributes` cho phép mở rộng metadata mà không phải đổi schema liên tục.

## 5. Ghi chú quan trọng

- Hiện backend và DB đã sẵn sàng cho `ESP32-S3 + ThingsBoard + web hosting` theo kiểu động.
- Nếu firmware stream-only chưa tự gọi provisioning sync, backend vẫn có thể tự thấy device mới qua ThingsBoard sync nền.
- Khi tài liệu cũ nói `http://<ip>/stream`, mặc định mới phải hiểu là `http://<host>:<port><path>` và thường là `http://<ip>:81/stream`.
