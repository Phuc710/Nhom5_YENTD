# ESP32-S3 Firmware Walkthrough

Tài liệu này mô tả trạng thái firmware ESP32-S3 hiện tại trong repo.

## 1. Trạng thái hiện tại

Firmware đang ưu tiên vai trò:

- kết nối WiFi
- phát MJPEG stream cục bộ
- tối ưu camera OV5640 cho stream

Phần backend/DB/ThingsBoard hiện đã sẵn sàng cho identity động, nhưng không phải mọi flow MQTT/provisioning cũ đều còn là luồng runtime chính của firmware hiện tại.

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

## 5. Quan hệ với backend và ThingsBoard

Phía backend/DB hiện hỗ trợ các field động sau nếu firmware gửi:

- `device_name`
- `project_name`
- `device_model`
- `wifi_ssid`
- `resolution`
- `stream_scheme`
- `stream_host`
- `stream_port`
- `stream_path`
- `stream_snapshot_path`
- `last_boot_at`

Nếu firmware chưa gửi các field này, backend vẫn có thể nhìn thấy camera qua ThingsBoard sync hoặc qua cấu hình tay trong DB.

## 6. Lưu ý khi đọc docs cũ

Nhiều doc cũ trong thư mục `docs/esp32-s3-devkitc-1` mô tả:

- MQTT ThingsBoard
- provisioning
- OTA

Các phần đó nên xem là:

- tài liệu lịch sử của firmware đời trước, hoặc
- tài liệu thiết kế nếu ta bật lại các capability đó

Khi có mâu thuẫn, ưu tiên code firmware hiện tại.
