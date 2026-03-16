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

Frontend PHP/JS (OOP & Grok UI)
    -> gọi backend qua REST API
    -> kết nối WebSockets tới ThingsBoard (thông qua proxy/cấu hình từ backend) để nhận Telemetry Real-time
    -> nhận Bounding Box AI Overlay qua Server-Sent Events (SSE)
    -> không gọi hoặc giữ khóa ThingsBoard tĩnh ở Web
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
- cung cấp API dashboard (Thống kê thực 100% qua Database, không mock)
- lưu violation và ảnh nghiệp vụ

## 3. Luồng dữ liệu chuẩn

### Luồng A: đăng ký và đồng bộ camera

1. Device xuất hiện trên ThingsBoard hoặc gọi provisioning sync về backend.
2. Backend upsert `cameras` và `camera_provisioning`.
3. **Identity Chain**: Hệ thống ưu tiên khớp theo **`mac_address`** (Hard Anchor) ➔ `camera_id` (Business) ➔ `tb_device_name` (IoT).
4. **Chuẩn hóa**: Backend tự động map `Light_Mode` ➔ `light_mode`, `idf_ver` ➔ `idf_version` và chuẩn hóa giá trị về **lowercase**.
5. DB tự chuẩn hóa tên hiển thị theo thứ tự: `camera_name -> tb_device_name -> device_name -> Camera 00x`.
6. Web đọc `view_camera_summary` và tự động cập nhật.

### Luồng B: Luồng Stream Đa Kênh (Zero-CPU Asyncio Pub/Sub)

1. ESP32 phát stream cục bộ lên mạng LAN.
2. Backend (`StreamWorker`) đứng ra làm Proxy duy nhất kết nối vào ESP32 để kéo MJPEG frame về.
3. Thay vì forward trực tiếp (gây sập ESP32 hoặc thắt cổ chai CPU), Backend lưu frame vào **Memory Cache** và sử dụng kiến trúc **Asyncio Queue Publish/Subscribe**.
4. Khi Frontend gọi API `/api/cameras/{id}/stream`, Backend sẽ phân phối luồng Stream từ RAM cho hàng trăm Client cùng lúc mà không tốn thêm % CPU nào của hệ thống.
5. Khi Frontend gọi API `/api/cameras/{id}/live-view/sse`, Backend dùng **Server-Sent Events** đẩy tọa độ Bounding Boxes của AI về Web đồng bộ với Video gốc.

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
