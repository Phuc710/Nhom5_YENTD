# Tổng Quan Hệ Thống (Backend Architecture)

## 1. Kiến trúc hiện tại

Hệ thống được thiết kế theo mô hình phân lớp để đảm bảo tính ổn định và khả năng mở rộng:

```text
ESP32-S3 Camera
    -> Phát MJPEG stream nội bộ (LAN).
    -> Tự động đồng bộ thông tin định danh (Provisioning/Identity) về Backend.
    -> Được quản lý tập trung bởi ThingsBoard ở lớp thiết bị.

ThingsBoard
    -> Quản lý danh tính thiết bị (Device Identity), thuộc tính (Attributes), điều khiển từ xa (RPC) và cập nhật OTA.
    -> Đóng vai trò lớp điều phối thiết bị (Device Orchestration).

Backend (FastAPI)
    -> Đồng bộ danh sách camera từ ThingsBoard hoặc qua cơ chế Provisioning trực tiếp.
    -> Làm Proxy cho luồng Stream và Snapshot để phục vụ giao diện Web.
    -> Quản lý nghiệp vụ: Camera, vùng nhận diện (Zones), hồ sơ vi phạm (Violations) và Dashboard.
    -> Chuẩn hóa dữ liệu thô thành thông tin nghiệp vụ cho Frontend.

Cơ sở dữ liệu (Supabase / PostgreSQL)
    -> Lưu trữ thông tin Camera (`cameras`).
    -> Lưu trữ lịch sử Provisioning (`camera_provisioning`).
    -> Lưu trữ các vùng cấu hình (`detection_zones`).
    -> Lưu trữ thông tin vi phạm và kết quả nhận diện biển số (`violations`, `ocr_results`).

Frontend (PHP/JS với Kiến trúc OOP)
    -> Truy xuất dữ liệu qua các REST API của Backend.
    -> Hiển thị tọa độ nhận diện AI (Bounding Boxes) thời gian thực qua Server-Sent Events (SSE).
    -> Giao diện Dashboard thống kê và Live View tập trung.
```

## 2. Vai trò của Backend

Backend đóng vai trò là lớp "trung tâm điều phối", giúp giao diện Web không bị phụ thuộc vào các yếu tố thay đổi liên tục:

- **Địa chỉ IP nội bộ**: Tự động cập nhật khi thiết bị khởi động lại.
- **Tên thiết bị**: Chuyển đổi từ mã kỹ thuật sang tên gọi nghiệp vụ dễ hiểu.
- **Dữ liệu thô**: Chuyển đổi JSON phức tạp từ ThingsBoard thành các Model dữ liệu tinh gọn.
- **Bảo mật**: Che giấu các Access Token và thông tin nhạy cảm của hệ thống IoT.

Các nhiệm vụ chính của Backend:
- Quản lý vòng đời (CRUD) của Camera và các vùng nhận diện.
- Đồng bộ danh sách thiết bị từ ThingsBoard (chế độ Best-effort).
- Chuẩn hóa URL luồng stream và cơ chế chụp ảnh (Snapshot).
- Làm Proxy truyền dẫn MJPEG để đảm bảo Web có thể xem được stream LAN.
- Cung cấp API Dashboard với số liệu thống kê thực tế từ Database.

## 3. Luồng dữ liệu tiêu chuẩn

### Luồng A: Đăng ký và Đồng bộ Camera
1. Thiết bị xuất hiện trên ThingsBoard hoặc gửi yêu cầu Provisioning trực tiếp về Backend.
2. Backend tự động cập nhật (Upsert) vào bảng `cameras` và `camera_provisioning`.
3. **Identity Chain (Chuỗi định danh)**: Ưu tiên khớp theo: **Địa chỉ MAC** (Định danh cứng) ➔ `camera_id` (Nghiệp vụ) ➔ `tb_device_name` (IoT ID).
4. **Chuẩn hóa**: Backend tự động ánh xạ các thuộc tính hệ thống (ví dụ: `Light_Mode` ➔ `light_mode`) và đưa về định dạng chữ thường (lowercase).
5. Tên hiển thị được ưu tiên theo thứ tự: `camera_name` (DB) ➔ `tb_device_name` ➔ `device_name` ➔ Mặc định.

### Luồng B: Luồng Stream Đa Kênh (Zero-CPU Asyncio)
1. ESP32 phát stream MJPEG trong mạng nội bộ.
2. Backend (`StreamWorker`) đóng vai trò là Proxy kết nối duy nhất vào thiết bị để lấy các khung hình (Frame).
3. Để bảo vệ ESP32 và tiết kiệm băng thông, Backend lưu frame vào bộ nhớ tạm (Memory Cache) và sử dụng kiến trúc **Asyncio Queue Pub/Sub**.
4. Khi hàng trăm người cùng xem trên Web, Backend sẽ phân phối dữ liệu từ RAM, không gây tải thêm cho thiết bị ESP32 hay CPU của máy chủ.
5. Tọa độ AI được đẩy về đồng bộ qua **Server-Sent Events (SSE)**.

### Luồng C: Ghi đè cấu hình thủ công (Override)
Nếu cần thiết lập đặc biệt, bạn có thể chỉnh sửa trực tiếp trong bảng `cameras`:
- Đặt lại tên camera (`camera_name`).
- Đặt lại URL stream (`stream_url`).
Các thiết lập thủ công này sẽ luôn được ưu tiên cao nhất.

## 4. Những điểm chuẩn hóa mới
- **Định danh động**: Không sử dụng tên model cứng để quản lý thiết bị.
- **URL linh hoạt**: Tự động dựng URL stream từ các thành phần `scheme`, `host`, `port`, `path`.
- **Mở rộng linh hoạt**: Trường `extra_attributes` cho phép lưu thêm metadata mà không cần thay đổi cấu trúc bảng.

## 5. Ghi chú quan trọng
- Hệ thống đã sẵn sàng cho mô hình vận hành động hoàn toàn.
- Nếu Firmware cũ chỉ hỗ trợ stream, Backend vẫn có thể tự động nhận dạng qua đồng bộ nền với ThingsBoard.
- Mọi tài liệu tham chiếu URL stream kiểu cũ `http://<ip>/stream` nên được hiểu theo cấu trúc mới là `http://<ip>:81/stream` (hoặc cổng cấu hình tương ứng).

---
Xem thêm: [Database Schema](./04_BACKEND_DATABASE.md) | [API Contracts](./02_BACKEND_API_V1.md)
