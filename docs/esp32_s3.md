# ESP32-S3 Firmware Walkthrough

Tài liệu này mô tả trạng thái firmware ESP32-S3 hiện tại trong repo.

## 1. Trạng thái hiện tại

Firmware hoạt động ổn định với các tính năng:

- **Kết nối WiFi**: Tự động kết nối hoặc bật Captive Portal cấu hình.
- **ThingsBoard MQTT**: Đồng bộ Attributes, Telemetry và xử lý RPC lệnh điều khiển.
- **Backend Sync**: Tự động đăng ký (`provision`) và gửi `heartbeat` lên Custom Backend.
- **Local Stream**: Phát MJPEG stream tại cổng 81 (`/stream`, `/snapshot`).
- **Hardware Integration**: Điều khiển Camera OV5640, Đèn giao thông (Traffic Light) và LED trạng thái RGB.

## 2. Các file chính đang quan trọng

- [main.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/main.c)
- [stream_server.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/stream_server.c)
- [task_manager.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/task_manager.c)
- [camera_task.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/camera_task.c)
- [goouuu_camera.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/goouuu_camera.c)
- [app_config.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/app_config.c)
- [wifi_manager.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/wifi_manager.c)

## 3. Stream hiện tại

ESP32 hiện phát:

- `GET http://<ip>:81/`
- `GET http://<ip>:81/snapshot`
- `GET http://<ip>:81/stream`

Camera profile hiện ưu tiên:

- `PIXFORMAT_JPEG`
- `FRAMESIZE_VGA`
- `jpeg_quality = 10`
- `fb_count = 2` nếu đủ PSRAM
- `CAMERA_GRAB_LATEST`
- anti-blur tuning bằng manual exposure/gain

## 4. Tên thiết bị

Firmware có `project_name` trong app descriptor.

Ví dụ hiện tại:

- `project(esp32-s3-cam-firmware)` trong `CMakeLists.txt`

Tên này có thể được backend dùng làm fallback hiển thị nếu provisioning sync gửi lên `project_name`.

## 5. Quan hệ với Backend và ThingsBoard (Identity Chain)

Hệ thống sử dụng **Identity Chain chuẩn** để quản lý thiết bị:
**`mac_address`** ➔ **`camera_id`** ➔ **`tb_device_name`**

### Cơ chế Tự động Đồng bộ (Auto Provisioning)
Khi ESP32 gửi dữ liệu, Backend thực hiện:
1. **Khớp MAC**: Tìm thiết bị cũ theo MAC để giữ lại lịch sử vi phạm.
2. **Chuẩn hóa Key**:
   - `Light_Mode` ➔ `light_mode`
   - `idf_ver` ➔ `idf_version`
3. **Chuẩn hóa Value**: Chuyển các giá trị Enum (`RED`, `ONLINE`) về **lowercase** (`red`, `online`).

## 6. Tài liệu Kỹ thuật Chi tiết

Để hiểu sâu hơn về từng module, vui lòng tham khảo các tài liệu "chuẩn" mới nhất:

- [Provisioning & Identity](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/02_PROVISIONING_AND_IDENTITY.md)
- [MQTT, Attributes & RPC](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
- [Health Telemetry](/C:/Users/Phucc/Desktop/ytd/docs/esp32-s3-devkitc-1/07_HEALTH_TELEMETRY.md)
- [Backend Sync & Heartbeat](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md)
- [Architecture & Matching Rules](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/01_ARCHITECTURE_AND_MATCHING.md)
