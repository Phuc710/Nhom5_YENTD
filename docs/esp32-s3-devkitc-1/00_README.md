# 00 - README

Tài liệu firmware cho board ESP32-S3 camera trong repo.

## 1. Trạng thái cần hiểu đúng

Firmware hiện tại trong repo đang đi theo hướng `stream-first`:

- kết nối WiFi
- mở stream MJPEG cục bộ
- tối ưu camera OV5640

Tài liệu chuyên sâu về từng module:
- [Provisioning & Identity](../thingsboard/02_PROVISIONING_AND_IDENTITY.md)
- [MQTT & Telemetry](../thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
- [Health Monitoring](./07_HEALTH_TELEMETRY.md)

## 2. Stream cục bộ

ESP32 hiện mở:

- `GET http://<ip>:81/`
- `GET http://<ip>:81/snapshot`
- `GET http://<ip>:81/stream`

## 3. Camera profile hiện tại

Luồng camera hiện ưu tiên:

- JPEG
- VGA
- quality 10
- PSRAM frame buffer
- anti-motion-blur tuning

## 4. Liên hệ với backend

- `camera_id`
- `tb_device_name`
- `mac_address`
- `ip_address`
- `stream_url`
- `device_state`
- `light_state`
- `location`

Mục tiêu là để web/backend không hardcode tên camera hay URL stream.

## 5. Nên đọc gì tiếp

- [../../esp32-s3-devkitc-1/README.md](../../esp32-s3-devkitc-1/README.md) (Tài liệu kỹ thuật chính)
- [../../esp32_s3.md](../esp32_s3.md)
- [../thingsboard/00_README.md](../thingsboard/00_README.md)
- [../../database/schema.sql](../../database/schema.sql)
