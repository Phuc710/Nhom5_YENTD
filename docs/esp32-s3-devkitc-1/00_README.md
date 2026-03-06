# 00 — README (Index)

> ESP32-S3-CAM (GOOUUU Tech N16R8) — Firmware Documentation

## Thông tin board

| Thông số | Giá trị |
|---------|---------|
| SoC | ESP32-S3 (Xtensa LX7 dual-core 240MHz) |
| Flash | 16MB (N16) |
| PSRAM | 8MB OPI PSRAM (R8) |
| Camera | OV2640 |
| LED | WS2812B tích hợp (GPIO 48) |
| Button | BOOT (GPIO 0) |
| Framework | ESP-IDF v5.x |
| Build tool | PlatformIO |

---

## Tài liệu theo chức năng

| File | Chức năng |
|------|-----------|
| [01_BOOT_SEQUENCE.md](01_BOOT_SEQUENCE.md) | Trình tự boot 7 bước, LED màu, log mẫu |
| [02_PROVISIONING.md](02_PROVISIONING.md) | Đăng ký thiết bị ThingsBoard, lấy token |
| [03_OTA_UPDATE.md](03_OTA_UPDATE.md) | OTA không gián đoạn, dual partition, rollback |
| [04_THINGSBOARD_MQTT.md](04_THINGSBOARD_MQTT.md) | Kết nối MQTT, shared attrs, RPC methods |
| [05_CAMERA_CAPTURE.md](05_CAMERA_CAPTURE.md) | Camera config, chụp ảnh, đổi resolution |
| [06_IMAGE_UPLOAD.md](06_IMAGE_UPLOAD.md) | Upload HTTP + MinIO S3 SigV4 |
| [07_HEALTH_TELEMETRY.md](07_HEALTH_TELEMETRY.md) | Telemetry JSON, dashboard ThingsBoard |
| [08_CONFIG_SECRETS.md](08_CONFIG_SECRETS.md) | platformio.ini, NVS, bảo mật credentials |
| [09_BUTTON_FACTORY_RESET.md](09_BUTTON_FACTORY_RESET.md) | Giữ nút BOOT 3s → factory reset |
| [10_LED_STATUS.md](10_LED_STATUS.md) | WS2812 LED màu sắc theo trạng thái |

---

## Kiến trúc tổng quan

```
                    ThingsBoard (self-hosted Docker)
                    ┌─────────────────────────────┐
                    │  MQTT :1883                 │
                    │  HTTP :8080 (provision, OTA)│
                    └──────────┬──────────────────┘
                               │ MQTT
                    ┌──────────▼──────────────────┐
                    │      ESP32-S3-CAM            │
                    │                             │
                    │  ┌──────────┐ ┌──────────┐  │
                    │  │ camera_  │ │ mqtt_    │  │
                    │  │ task     │ │ task     │  │
                    │  └────┬─────┘ └──────────┘  │
                    │       │ g_frame_queue        │
                    │  ┌────▼─────┐ ┌──────────┐  │
                    │  │uploader_ │ │health_   │  │
                    │  │task      │ │task      │  │
                    │  └────┬─────┘ └──────────┘  │
                    │       │ HTTP POST            │
                    └───────┼─────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
   ┌──────────▼──────────┐   ┌────────────▼───────┐
   │  Backend API        │   │  MinIO / S3         │
   │  :3340/ocr/kafka    │   │  dev-s3.imespro.ai  │
   └─────────────────────┘   └────────────────────┘
```

---

## FreeRTOS Task Summary

| Task | Priority | Stack | Core |
|------|----------|-------|------|
| `button_task` | 8 | 2KB | Mặc định |
| `camera_task` | 7 | 6KB | Mặc định |
| `uploader_task` | 6 | 12KB | Mặc định |
| `mqtt_task` | 5 | 12KB | Mặc định |
| `health_task` | 4 | 4KB | Mặc định |

---

## Quickstart

```bash
# 1. Setup
cp platformio.ini.example platformio.ini
# Sửa IP, key trong platformio.ini

# 2. Build
cd esp32-s3-devkitc-1
idf.py set-target esp32s3
idf.py build

# 3. Flash
idf.py -p COM_PORT flash monitor
```

## Xem log real-time

```bash
idf.py -p COM_PORT monitor --baud 115200
```
