# 00 - README

> Tài liệu firmware cho `ESP32 Cam Kit Phát Triển ESP32-S3 N16R8 OV5640 Type-C` trong đồ án giám sát vi phạm giao thông

## 1. Vai trò của firmware

Firmware trên board chịu trách nhiệm:

- kết nối WiFi
- provision lên ThingsBoard để lấy token
- điều khiển đèn giao thông 3 màu
- nhận RPC đổi mode và timing
- chụp frame từ camera
- gắn trạng thái đèn vào từng frame ngay lúc chụp
- upload frame pha đỏ lên backend
- gọi `POST /api/finalize` khi chuyển `đỏ -> xanh`
- gọi `POST /api/upload/heartbeat` khi không ở pha đỏ
- gửi telemetry sức khỏe và trạng thái đèn lên ThingsBoard
- tự sync provisioning về backend sau khi MQTT kết nối

## 2. Profile phần cứng đang chốt

Board thực tế đang dùng:

- `ESP32 Cam Kit Phát Triển ESP32-S3 N16R8 OV5640 Type-C`
- SoC: `ESP32-S3-WROOM-1`
- CPU: `Xtensa LX7 dual-core 32-bit`, tối đa `240 MHz`
- ROM: `384 KB`
- SRAM: `512 KB`
- RTC SRAM: `16 KB`
- PSRAM: `8 MB`
- Flash: `16 MB`
- Camera: `OV5640`
- Điện áp hoạt động: `3.0V -> 3.6V`

Tài liệu chi tiết profile phần cứng nằm ở:

- [11_BOARD_PROFILE_N16R8_OV5640.md](11_BOARD_PROFILE_N16R8_OV5640.md)

## 3. Contract backend đang dùng

- `POST /api/upload`
  Chỉ dùng cho frame pha `red` hoặc `emergency_red`

- `POST /api/upload/heartbeat`
  Dùng khi đèn đang `green` hoặc `yellow` để giữ camera online trên dashboard

- `POST /api/finalize`
  Gọi khi firmware phát hiện chuyển pha `đỏ -> xanh`

- `POST /api/cameras/provision`
  Gọi sau khi MQTT kết nối để sync `camera_id + token + mac + ip + fw` về backend

Field chính của request upload:

- `camera_id`
- `traffic_light_state`
- `operation_mode`
- `tl_state_ms`
- `file`

## 4. Luồng vận hành chuẩn

```text
traffic_light + camera_task
    -> chụp frame
    -> gắn state/mode/state_ms vào frame_msg_t
    -> đẩy vào g_frame_queue

uploader_task
    -> nếu frame đỏ: POST /api/upload
    -> nếu frame không đỏ: heartbeat định kỳ
    -> nếu thấy chuyển đỏ -> xanh: POST /api/finalize
    -> nếu có cấu hình MinIO: lưu frame đỏ lên S3

mqtt_task
    -> MQTT connect ThingsBoard
    -> request shared attributes
    -> publish client attributes
    -> sync provisioning về backend
```

## 5. Tài liệu chi tiết

- [01_BOOT_SEQUENCE.md](01_BOOT_SEQUENCE.md)
- [02_PROVISIONING.md](02_PROVISIONING.md)
- [03_OTA_UPDATE.md](03_OTA_UPDATE.md)
- [04_THINGSBOARD_MQTT.md](04_THINGSBOARD_MQTT.md)
- [05_CAMERA_CAPTURE.md](05_CAMERA_CAPTURE.md)
- [06_IMAGE_UPLOAD.md](06_IMAGE_UPLOAD.md)
- [07_HEALTH_TELEMETRY.md](07_HEALTH_TELEMETRY.md)
- [08_CONFIG_SECRETS.md](08_CONFIG_SECRETS.md)
- [09_BUTTON_FACTORY_RESET.md](09_BUTTON_FACTORY_RESET.md)
- [10_LED_STATUS.md](10_LED_STATUS.md)
- [11_BOARD_PROFILE_N16R8_OV5640.md](11_BOARD_PROFILE_N16R8_OV5640.md)

## 6. Ghi chú triển khai

- `BACKEND_UPLOAD_URL` phải là base URL của backend, ví dụ `http://192.168.1.20:8000`
- firmware hiện không tự kết luận vi phạm; kết luận chính thức nằm ở backend
- ThingsBoard vẫn là nơi giữ RPC, shared attributes và telemetry vận hành
- frontend web cảnh sát chỉ nên gọi backend, không gọi trực tiếp ThingsBoard

## Cap nhat WiFi Manager

- Firmware khong con dung `DEFAULT_WIFI_SSID` / `DEFAULT_WIFI_PASS` de boot.
- WiFi van duoc luu trong NVS (`ssid`, `password`) va tu dong dung lai o lan boot sau.
- Neu NVS chua co WiFi hoac ket noi that bai, ESP32 se bat SoftAP config portal tai `http://192.168.4.1/`.
- SSID AP config lay tu `platformio.ini`: `wifi_ap_ssid = kaishop`.
- Neu `wifi_ap_pass` ngan hon 8 ky tu, ESP-IDF se bat `open AP`; gia tri `1` hien tai se roi vao truong hop nay.
