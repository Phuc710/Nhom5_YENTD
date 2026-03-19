# Tổng Quan Firmware ESP32-S3

Tài liệu này mô tả trạng thái và kiến trúc Firmware của thiết bị ESP32-S3 trong hệ thống.

## 1. Trạng thái hiện tại

Firmware hoạt động ổn định với các tính năng cốt lõi:

- **Kết nối WiFi**: Tự động kết nối tới WiFi đã lưu hoặc kích hoạt chế độ Captive Portal (Phát WiFi cấu hình) nếu chưa có mạng.
- **ThingsBoard MQTT**: Đồng bộ các thuộc tính (Attributes), dữ liệu cảm biến (Telemetry) và xử lý các lệnh điều khiển từ xa (RPC).
- **Đồng bộ Backend (Custom Sync)**: Tự động đăng ký thiết bị (`provision`) và gửi tín hiệu duy trì kết nối (`heartbeat`) lên Backend.
- **Phát Stream MJPEG**: Hỗ trợ xem trực tiếp qua mạng nội bộ tại cổng 81 (`/stream`, `/snapshot`).
- **Tích hợp phần cứng**: Điều khiển Camera OV5640, hệ thống đèn tín hiệu giao thông và đèn LED trạng thái RGB.

## 2. Các thành phần quan trọng

- `main.c`: Điểm khởi đầu và quản lý vòng đời ứng dụng.
- `wifi_manager.c`: Quản lý kết nối internet và giao diện cấu hình WiFi.
- `stream_server.c`: Xử lý luồng Video MJPEG gửi tới Backend/Web.
- `camera_task.c`: Quản lý việc lấy khung hình từ cảm biến ảnh.
- `app_config.c`: Quản lý các biến môi trường và thông tin định danh thiết bị.

## 3. Cấu hình luồng Stream

ESP32 hỗ trợ các Endpoint sau:
- `GET http://<ip>:81/stream`: Luồng Video liên tục.
- `GET http://<ip>:81/snapshot`: Chụp một ảnh duy nhất.

Thông số kỹ thuật mặc định:
- Định dạng ảnh: JPEG.
- Độ phân giải: VGA (640x480).
- Chất lượng ảnh: 10 (Nén tốt để giảm độ trễ).
- Chế độ phơi sáng: Tự động điều chỉnh để chống nhòe hình ảnh xe đang di chuyển.

## 4. Cơ chế Định danh (Identity Chain)

Thiết bị luôn tuân thủ chuỗi định danh tiêu chuẩn để Backend có thể quản lý chính xác:
**Địa chỉ MAC** ➔ **camera_id** ➔ **tb_device_name**

Mọi thay đổi về địa chỉ IP hoặc tên ngẫu nhiên của thiết bị đều không ảnh hưởng đến việc ghi nhận dữ liệu vi phạm, vì địa chỉ MAC được dùng làm mốc định danh "cứng".

## 5. Quy trình Đồng bộ Tự động (Auto Provisioning)

Mỗi khi khởi động hoặc thay đổi cấu hình LAN, ESP32 sẽ gửi báo cáo về Backend để:
1. **Khớp nối thiết bị**: Backend dùng MAC để tìm kiếm và giữ lại lịch sử nghiệp vụ cũ.
2. **Cập nhật IP**: Đảm bảo Backend luôn biết địa chỉ IP mới nhất để thực hiện Proxy Stream.
3. **Chuẩn hóa thông số**: Tự động chuyển đổi các trạng thái kỹ thuật (ví dụ: `Light_Mode`) sang định dạng nghiệp vụ của Backend.

---
Tài liệu tham khảo kỹ thuật: [Cấu hình đồng bộ](./09_UNIFIED_CONFIG_SYNC.md) | [Hướng dẫn nạp code](./esp32-s3-devkitc-1/08_CONFIG_SECRETS.md)
