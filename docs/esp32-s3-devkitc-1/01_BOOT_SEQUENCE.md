# 01 — Boot Sequence (Trình tự khởi động)

## Tổng quan

Mỗi lần cấp điện hoặc `esp_restart()`, ESP32-S3 thực thi `app_main()` trong `src/main.c`.  
Boot chia làm **7 bước tuần tự**, mỗi bước thất bại nghiêm trọng → log lỗi → `esp_restart()` sau 3–5s (tránh boot loop vô hạn).

---

## Flow chi tiết

```
Cấp nguồn / esp_restart()
        │
        ▼
┌─────────────────────────────────┐
│ [1] nvs_flash_init()            │  ← Xóa NVS nếu version mới hoặc bị lỗi
│     → Khởi tạo Non-Volatile     │
│       Storage (NVS flash)       │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ [2] app_config_load()           │  ← Đọc cấu hình từ NVS
│     Kết quả:                    │
│     EMPTY   → set defaults      │
│     VALID   → dùng luôn         │
│     MIGRATE → cần nâng version  │
│                                 │
│     Cấu trúc app_config_t:      │
│       ssid, password            │
│       token (TB access token)   │
│ provisioning_key, provisioning_secret │
│       frames_per_upload         │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ [3] led_status_init()           │  ← GPIO 48 WS2812 RGB LED
│     → led_status_set_rgb(8,8,8) │    Trắng mờ = đang boot
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ [4] wifi_manager_ensure_connected() │ ← Thu STA, roi fallback AP portal neu can
│     SSID/pass doc tu NVS            │    AP config: 192.168.4.1
│     Khong con DEFAULT_WIFI_*        │
│                                 │
│     LED:  Vàng nhạt = đang kết  │
│           Xanh lá = thành công  │
│           Đỏ = thất bại         │
│     Thất bại → esp_restart()    │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ [5] Provisioning (nếu cần)      │  ← Chỉ chạy nếu NVS không có token
│     tb_has_token() == false      │
│     tb_provision_device()        │
│     Xem: 02_PROVISIONING.md      │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ [6] task_manager_init(token)    │  ← Tạo queues + khởi tạo camera
│     Tạo:                        │      + start 5 FreeRTOS tasks
│       g_frame_queue      (3)    │
│       g_mqtt_cmd_queue   (4)    │
│       g_telemetry_queue  (8)    │
│       g_latest_frame_mutex      │
│                                 │
│     Start tasks:                │
│       camera_task    P=7        │
│       uploader_task  P=6        │
│       mqtt_task      P=5        │
│       health_task    P=4        │
│       button_task    P=8        │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ [7] OTA Rollback Protection     │  ← esp_ota_mark_app_valid_cancel_rollback()
│     Nếu partition state =       │    Báo firmware mới này hợp lệ
│     PENDING_VERIFY → mark valid │    Nếu không gọi trước timeout
│                                 │    → tự rollback về firmware cũ
└─────────────┬───────────────────┘
              │
              ▼
       led_status_white()          ← LED trắng = hệ thống chạy bình thường
       app_main() returns          ← FreeRTOS scheduler tiếp quản
              │
    ┌─────────┴────────┐
    camera_task     mqtt_task
    uploader_task   health_task
    button_task
```

---

## LED màu trong quá trình boot

| Màu | Ý nghĩa |
|-----|---------|
| Trắng mờ `(8,8,8)` | Đang boot |
| Vàng nhạt `(32,24,0)` | Đang kết nối WiFi |
| Xanh lá `(0,48,0)` | WiFi thành công |
| Đỏ `(48,0,0)` | WiFi thất bại |
| Cyan `(0,32,32)` | Đang provisioning |
| Xanh lam nhạt `(0,16,32)` | Đang start tasks |
| Trắng đầy `(32,32,32)` | Hệ thống sẵn sàng |

---

## Log mẫu (Serial Monitor 115200 baud)

```
I main: ======================================
I main:   ESP32-S3-CAM Firmware boot
I main: ======================================
I main: [1/7] NVS khởi tạo OK
I main: [2/7] Config SSID=MyWiFi Token=(có)
I main: [3/7] LED RGB khởi tạo OK
I main: [4/7] WiFi đã kết nối
I main: [5/7] Đã có token, bỏ qua provisioning
I main: [6/7] Tất cả task đã khởi động
I main: [7/7] Firmware đã xác nhận hợp lệ (OTA rollback protection)
I main: Firmware: esp32-s3-cam v1.0.0 | Build: Mar 06 2026 14:00:00
I main: ======================================
I main:   Khởi động hoàn tất!
```

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/main.c` | Entry point — 7 bước boot |
| `include/app_config.h` | Struct cấu hình NVS |
| `src/app_config.c` | Load/save NVS |
| `src/task_manager.c` | Khởi tạo queues & tasks |
| `src/wifi_manager.c` | Kết nối WiFi STA |
| `src/led_status.c` | LED RGB feedback |

## Cap nhat WiFi Manager

Tu firmware cap nhat ngay `2026-03-09`, buoc `[4]` khong con la `wifi_connect_with_retry()` voi build-time SSID/password nua.

Flow moi:

1. Thu ket noi bang WiFi da luu trong NVS.
2. Neu that bai hoac chua co WiFi, bat AP config portal.
3. User vao `http://192.168.4.1/`, scan WiFi, nhap mat khau, luu vao NVS.
4. ESP32 thu ket noi lai ngay va tat AP neu thanh cong.

AP config hien dang lay tu `platformio.ini`:

- `wifi_ap_ssid = kaishop`
- `wifi_ap_pass = 1`

Luu y: mat khau SoftAP ngan hon 8 ky tu se khong bat duoc WPA2 trong ESP-IDF, nen firmware se phat `open AP`.
