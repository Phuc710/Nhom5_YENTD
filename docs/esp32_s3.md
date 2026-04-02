# Tổng Quan Firmware ESP32-S3

Tài liệu này mô tả trạng thái và kiến trúc Firmware của thiết bị ESP32-S3 trong hệ thống.

## 1. Trạng thái hiện tại

Firmware hoạt động ổn định với các tính năng cốt lõi:

- **Trình diện Chuẩn Maintainer**: Tách biệt luồng Điều khiển (Control Plane - MQTT) và luồng Dữ liệu (Data Plane - HTTP Sync).
- **ThingsBoard MQTT**: Đồng bộ Attributes, Telemetry và xử lý RPC (Reboot, OTA, Trigger).
- **Backend Sync (HTTP)**: Tự động đăng ký (`provision`) và gửi nhịp tim (`heartbeat`) siêu nhẹ lên AI Backend. Bổ sung cơ chế **Circuit Breaker** tự ngắt khi Backend quá tải.
- **Phát Stream MJPEG**: Hỗ trợ xem trực tiếp và AI Processing tại cổng 81 (`/stream`).
- **Tích hợp phần cứng**: Điều khiển Camera, hệ thống đèn giao thông và tính năng **Hardware Factory Reset** (nhấn giữ nút BOOT).

## 2. Các thành phần quan trọng

- `main.c`: Bootstrapper tinh gọn, khởi tạo phần cứng và trao quyền cho Task Manager.
- `backend_sync.c`: Xử lý HTTP Provisioning/Heartbeat tách biệt, không gây block MQTT.
- `mqtt_app.c`: Chỉ quản lý kết nối MQTT và logic ThingsBoard.
- `wifi_manager.c`: Quản lý kết nối internet và giao diện cấu hình WiFi.
- `stream_server.c`: Xử lý luồng Video MJPEG gửi tới Backend/Web.
- `health_task.c`: Giám sát sức khỏe thiết bị bằng formal State Machine (Enum).
- `app_config.c`: Quản lý cấu hình NVS và identity.

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
1. **Khớp nối thiết bị**: Backend dùng MAC để định danh "cứng" thiết bị.
2. **Cập nhật IP**: Đảm bảo Backend luôn biết địa chỉ IP mới nhất để Proxy Stream.
3. **Chuẩn hóa thông số**: Tự động chuyển đổi các trạng thái kỹ thuật (`light_state`, `device_state`) sang định dạng nghiệp vụ của Backend.
4. **Tự cứu hộ**: Nếu Backend lỗi, thiết bị rơi vào `DEGRADED` mode để bảo vệ tài nguyện mạng.

---
Tài liệu tham khảo kỹ thuật: [Cấu hình đồng bộ](./09_UNIFIED_CONFIG_SYNC.md) | [Hướng dẫn nạp code](./esp32-s3-devkitc-1/08_CONFIG_SECRETS.md)
