# 03 — OTA Update (Over-the-Air Firmware Update)

## Tổng quan

Firmware hỗ trợ **OTA không gián đoạn camera** — khi đang tải firmware mới, camera task và uploader task **vẫn tiếp tục hoạt động** bình thường.  
ESP32-S3 N16R8 dùng **dual partition** (app0 + app1, mỗi cái 3MB), hỗ trợ **tự rollback** nếu firmware mới bị lỗi.

---

## Partition Layout (16MB Flash)

```
┌──────────┬──────────┬─────────────────────┬─────────────────────┬──────────────────┐
│  nvs     │ otadata  │      app0 (OTA_0)   │      app1 (OTA_1)   │     spiffs       │
│  20KB    │   8KB    │        3MB          │        3MB          │      8.25MB      │
│ 0x9000   │ 0xe000   │      0x10000        │      0x310000       │    0x610000      │
└──────────┴──────────┴─────────────────────┴─────────────────────┴──────────────────┘
```

- **otadata**: lưu trạng thái partition nào đang active và trạng thái OTA
- **app0/app1**: luân phiên — đang chạy app0 → OTA ghi vào app1, và ngược lại
- Firmware tối đa ~3MB

---

## 2 Cách kích hoạt OTA

### Cách 1: ThingsBoard OTA Package (Khuyến nghị cho production)
ThingsBoard gửi `fw_title` + `fw_version` qua **Shared Attributes**:
```json
{
  "fw_title": "esp32-s3-cam",
  "fw_version": "1.2.0"
}
```
Firmware tự build URL download:
```
http://<TB_HOST>:9090/api/v1/<TOKEN>/firmware?title=esp32-s3-cam&version=1.2.0
```

### Cách 2: Gửi URL trực tiếp qua Shared Attribute hoặc RPC
```json
// Shared Attribute:
{ "ota_url": "http://my-server.com/firmware_v1.2.0.bin" }

// Hoặc RPC:
{ "method": "startOTA", "params": { "url": "http://my-server.com/fw.bin" } }
```

---

## Flow chi tiết OTA

```
ThingsBoard → MQTT → mqtt_event_handler (MQTT_EVENT_DATA)
        │
        ▼
handle_attributes() hoặc handle_rpc()
        │
        ├─ So sánh fw_version với esp_app_get_description()->version
        │         Giống → bỏ qua
        │         Khác  → tiếp tục
        │
        └─ start_ota(url):
                │
                ▼
         s_ota_active = true
         copy URL string (strdup)
                │
                ▼
         xTaskCreate(ota_task, stack=8192, priority=3)
                │
                │  ← Camera task VẪN CHỤP ẢNH (priority=7)
                │  ← Uploader task VẪN UPLOAD (priority=6)
                │  ← MQTT task VẪN NHẬN LỆNH (priority=5)
                │
                ▼
         ota_task():
           LED → Xanh dương (0,0,64)
           Publish fw_state = "DOWNLOADING"
                │
                ▼
         esp_https_ota(&ota_config)
           HTTP(S) GET → tải từng chunk → ghi vào partition inactive
                │
         ┌──────┴──────┐
      Success        Failure
         │               │
         ▼               ▼
  Publish             Publish
  fw_state=           fw_state=
  "UPDATED"           "FAILED"
  LED → Xanh lá       LED → Đỏ
  esp_restart()       s_ota_active=false (tiếp tục chạy old fw)
```

---

## Rollback Protection (Bảo vệ tự động)

### Cơ chế:
1. Sau khi OTA thành công và reboot, firmware mới chạy với partition state = `PENDING_VERIFY`
2. `app_main()` bước [7] gọi `esp_ota_mark_app_valid_cancel_rollback()` → state = `VALID`
3. Nếu firmware mới **crash trước bước [7]** → Bootloader tự rollback về firmware cũ

### Timeline rollback:
```
Boot mới (fw v1.2.0)
    │
    ▼
[1][2][3]... ESP32 chạy bình thường
    │
    ▼
[7] esp_ota_mark_app_valid_cancel_rollback()
    │                │
  Thành công    Crash/hang trước đây
    │                │
    ▼                ▼
Firmware v1.2.0  Bootloader detect PENDING_VERIFY
bình thường      → Boot lại với firmware cũ (v1.1.0)
```

---

## Trạng thái OTA báo về ThingsBoard

### Client Attribute:
```json
{ "fw_state": "DOWNLOADING" }  // đang tải
{ "fw_state": "UPDATED" }       // thành công, sắp reboot
{ "fw_state": "FAILED", "fw_error": "esp_https_ota error" }
```

### Telemetry sau khi reboot:
```json
{ "status": "online" }  // MQTT reconnect sau boot mới
```
Và firmware gửi Client Attribute mới với `fw_version` mới.

---

## Bảo mật OTA

- **HTTPS**: nếu URL dùng `https://` → tự động gắn Mozilla CA bundle (`esp_crt_bundle_attach`) → xác thực TLS server
- **HTTP**: dùng được với self-hosted server nội bộ
- **Không OTA 2 lần cùng version**: firmware so sánh `fw_version` với current running version trước khi bắt đầu
- **Không OTA khi đang OTA**: `s_ota_active` flag ngăn chạy 2 OTA song song

---

## Cấu hình ThingsBoard OTA Package

1. TB UI → **OTA Updates** → **Add OTA Package**
2. Điền: Title = `esp32-s3-cam`, Version = `1.2.0`
3. Upload file `firmware.bin` (từ `build/esp32-s3-cam-firmware.bin`)
4. Assign OTA package vào **Device Profile** → thiết bị sẽ nhận tự động

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/mqtt_app.c` | `handle_attributes()`, `start_ota()`, `ota_task()` |
| `src/main.c` | Bước [7]: `esp_ota_mark_app_valid_cancel_rollback()` |
| `partitions.csv` | Định nghĩa dual partition 3MB × 2 |
