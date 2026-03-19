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

Backend và DB hiện hỗ trợ nhận các field identity/runtime động nếu firmware gửi:

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

Mục tiêu là để web/backend không hardcode tên camera hay URL stream.

## 5. Nên đọc gì tiếp

- [../../esp32_s3.md](../esp32_s3.md)
- [../thingsboard/00_README.md](../thingsboard/00_README.md)
- [../../database/schema.sql](../../database/schema.sql)
