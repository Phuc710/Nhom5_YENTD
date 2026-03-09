ESP32-S3-CAM Firmware — Walkthrough
Tổng quan đã hoàn thành
Toàn bộ ESP-IDF firmware production-grade cho GOOUUU Tech ESP32-S3-CAM N16R8 với Vietnamese logs, ThingsBoard self-hosted, và OTA không gián đoạn camera.

Cấu trúc file sau khi hoàn thành
Headers (include/)
File	Vai trò
app_config.h
NVS config struct, magic/version constants
goouuu_board.h
GPIO pin map ESP32-S3 N16R8
goouuu_camera.h
Camera config defaults (PSRAM auto-detect)
led_status.h
RGB LED API
led_strip_encoder.h
WS2812 RMT encoder header
mqtt_app.h
MQTT API + TB topic constants + URLs
task_common.h
Shared structs: frame_msg_t, mqtt_cmd_msg_t, health_telemetry_t
task_manager.h
Task handles, queue handles, global state
tb_provisioning.h
ThingsBoard provisioning API
uploader_task.h
Upload task API
wifi_manager.h
WiFi connect API
Sources (src/)
File	Vai trò
main.c
Boot sequence 7 bước
app_config.c
NVS load/save/clear
wifi_manager.c
ESP-IDF STA WiFi + retry
led_status.c
WS2812 RMT GPIO 48
led_strip_encoder.c
WS2812 timing encoder
goouuu_camera.c
Camera init với PSRAM auto-detect
tb_provisioning.c
HTTP provisioning → lấy token
camera_task.c
Chụp ảnh định kỳ + fallback fake JPEG
mqtt_app.c
MQTT client đầy đủ
uploader_task.c
Upload HTTP + MinIO/S3
task_manager.c
Tạo queues + start tất cả tasks
health_task.c
Thu thập telemetry định kỳ
button_task.c
Long-press factory reset
CMakeLists.txt
ESP-IDF component registration
ThingsBoard Attributes & Telemetry
Shared Attributes (đọc từ TB server)
Key	Mô tả
fw_version	OTA: so sánh với firmware hiện tại
fw_title	OTA: title để build download URL
ota_url / fw_url	OTA: URL trực tiếp
active / save_img	Bật/tắt lưu ảnh
frames_per_upload	Giới hạn số frame upload MinIO
jpeg_quality	Gửi lệnh đổi JPEG quality camera
resolution	Gửi lệnh đổi framesize camera
reboot	Khởi động lại thiết bị
factory_reset / 
reset
Factory reset NVS
camera_id / cam_id	ID camera
inactivityAlarmTime	Đọc nhưng không xử lý (TB built-in)
Telemetry (gửi lên TB)
Key	Mô tả
upload_ok	Lần upload cuối thành công
last_http_code	HTTP status code cuối
latency_ms	Độ trễ upload (ms)
Wifi_Status	RSSI (dBm)
free_heap	Heap tự do
min_free_heap	Heap thấp nhất
frame_count	Tổng frame đã chụp
send_success / 
send_fail
Thống kê upload
uptime_sec	Thời gian hoạt động
camera_ok	Camera đang hoạt động
net_error	Đang có lỗi mạng
Client Attributes (thiết bị → TB)
Key	Mô tả
Model	"GOOUUU Tech ESP32-S3-CAM N16R8"
fw_version	Phiên bản firmware
camera_id	ID camera
mac
MAC address WiFi STA
idf_ver	Phiên bản ESP-IDF
Flow: OTA Update (không gián đoạn camera)
ThingsBoard → MQTT shared attributes: fw_title, fw_version
         ↓
mqtt_app.c: so sánh version, build URL:
  {TB_BASE_URL}/api/v1/{token}/firmware?title=...&version=...
         ↓
start_ota() → tạo FreeRTOS "ota" task stack=8192 priority=3
         ↓
ota_task(): esp_https_ota() chạy nền
  → Camera task VẪN CHỤP ẢNH BÌNH THƯỜNG
  → Uploader task VẪN UPLOAD BÌNH THƯỜNG
  → LED đổi sang xanh dương
  → Publish fw_state = "DOWNLOADING"
         ↓
Hoàn tất → fw_state = "UPDATED" → esp_restart()
         ↓
Boot mới: esp_ota_mark_app_valid_cancel_rollback()
  (nếu boot thất bại → tự rollback về firmware cũ)
Flow: Provisioning
main.c: token trống trong NVS
       ↓
tb_provision_device():
  HTTP POST {TB_URL}/api/v1/provision
  body: { deviceName: "cam-AABBCCDDEE", provisionDeviceKey, provisionDeviceSecret }
       ↓
Response 200: { credentialsValue: "<TOKEN>" }
       ↓
Lưu token vào NVS → task_manager_init(token)
       ↓
Nếu thất bại → mqtt_task tiếp tục thử mỗi 3 giây
Self-hosted Docker
ThingsBoard tự host từ 
docker-compose.yml
:

UI: http://<HOST>:9090
MQTT: <HOST>:1883
Provision URL: http://<HOST>:9090/api/v1/provision
Cập nhật IP trong các file:

include/mqtt_app.h
 → THINGSBOARD_BASE_URL và MQTT_BROKER_URI
include/tb_provisioning.h
 → TB_PROVISION_URL
Build
bash
cd esp32-cam
idf.py set-target esp32s3
idf.py build
idf.py -p COM_PORT flash monitor

WiFi Manager cap nhat:

- khong con lay WiFi build-time tu `DEFAULT_WIFI_SSID` / `DEFAULT_WIFI_PASS`
- neu chua co WiFi trong NVS hoac ket noi that bai, firmware tu bat AP config portal
- AP config lay tu `platformio.ini`, hien dang dat `wifi_ap_ssid = kaishop`
- `wifi_ap_pass = 1` se duoc xu ly thanh `open AP` do gioi han SoftAP cua ESP-IDF

Contract backend hiện tại

- upload ảnh thật: `POST /api/upload`
- heartbeat khi không ở pha đỏ: `POST /api/upload/heartbeat`
- chốt buffer khi chuyển `đỏ -> xanh`: `POST /api/finalize`
- field upload quan trọng: `camera_id`, `traffic_light_state`, `operation_mode`, `tl_state_ms`, `file`

Tài liệu chuẩn phần ThingsBoard

- [`thingsboard/00_README.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/00_README.md)
- [`thingsboard/02_PROVISIONING_AND_IDENTITY.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/02_PROVISIONING_AND_IDENTITY.md)
- [`thingsboard/03_MQTT_ATTRIBUTES_RPC.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
- [`thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md)
