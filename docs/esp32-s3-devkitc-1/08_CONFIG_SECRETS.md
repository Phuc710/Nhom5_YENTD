# 08 - Config And Secrets

## Trạng thái hiện tại

Firmware stream-first hiện chủ yếu dùng:

1. build-time defaults
2. NVS runtime config

ThingsBoard/shared attributes chỉ là capability mở rộng nếu bật lại.

## 1. Build-time config

Nguồn:

- `platformio.ini`
- `platformio.ini.example`

Những nhóm cấu hình còn hữu ích:

- WiFi AP fallback
- camera defaults
- board/profile defaults

## 2. NVS runtime config

NVS hiện là nơi nên giữ:

- WiFi SSID/password
- các cấu hình runtime thật sự cần cho boot lần sau

## 3. Secrets

Nguyên tắc:

- không commit `platformio.ini` thật nếu có secret
- dùng `platformio.ini.example` để chia sẻ
- không hardcode domain/backend URL vào docs nếu deployment có thể đổi

## 4. Nếu bật provisioning sync

Khi cần, có thể gửi động về backend:

- `device_name`
- `project_name`
- `device_model`
- `wifi_ssid`
- `resolution`
- `stream_host`
- `stream_port`
- `stream_path`

thay vì cố định trong build flags.
