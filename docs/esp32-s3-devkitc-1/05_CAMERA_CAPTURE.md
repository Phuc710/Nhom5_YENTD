# 05 — Camera & Capture Task

## Tổng quan

`camera_task` chụp ảnh định kỳ, đẩy JPEG vào `g_frame_queue` để `uploader_task` upload lên backend.  

---

## Cấu hình camera mặc định

```c
camera_config_t cfg = {
    // Chân GPIO (GOOUUU N16R8)
    .pin_pwdn    = CAM_PIN_PWDN,   // -1 (không dùng)
    .pin_reset   = CAM_PIN_RESET,  // -1 (không dùng)
    .pin_xclk    = CAM_PIN_XCLK,   // GPIO 15
    .pin_sccb_sda= CAM_PIN_SIOD,   // GPIO 4
    .pin_sccb_scl= CAM_PIN_SIOC,   // GPIO 5
    .pin_d7..d0  = GPIO 16,17,18,12,10,8,9,11
    .pin_vsync   = GPIO 6
    .pin_href    = GPIO 7
    .pin_pclk    = GPIO 13

    .xclk_freq_hz = 20000000,       // 20 MHz
    .ledc_timer   = LEDC_TIMER_0,
    .ledc_channel = LEDC_CHANNEL_0,

    .pixel_format = PIXFORMAT_JPEG,
    .frame_size   = FRAMESIZE_VGA,  // 640×480
    .jpeg_quality = 10,             // 1=tốt nhất, 63=kém nhất
    .fb_count     = 2,              // Double buffer (cần PSRAM)
    .grab_mode    = CAMERA_GRAB_LATEST,  // Luôn lấy frame mới nhất
    .fb_location  = CAMERA_FB_IN_PSRAM, // Frame buffer trong PSRAM 8MB
};
```

### Tại sao `CAMERA_GRAB_LATEST`?
- Tránh trường hợp queue camera đầy frame cũ → nhận ảnh bị trễ
- Phù hợp nhận diện giao thông real-time

### Tại sao `fb_count=2`?
- Camera ghi vào buffer 1 trong khi code đọc buffer 2 → không bị tearing
- Yêu cầu PSRAM (N16R8 có 8MB PSRAM → đủ)

---

## Flow `camera_task`

```
camera_task() khởi động
        │
        ▼
Vòng lặp (vTaskDelayUntil = g_capture_interval_ms)
        │
        ├─ [A] Kiểm tra lệnh MQTT từ g_mqtt_cmd_queue
        │      (CAMERA_RESOLUTION, CAMERA_QUALITY) → apply ngay
        │
        ├─ [B] esp_camera_fb_get()
        │       │
        │     NULL ── fail_streak++ ──► 3 lần liên tiếp
        │       │                       → s_fake_mode = true
        │       │                       → g_camera_ok = false
        │       │
        │     OK  ── g_camera_ok = true ── g_frame_count++
        │
        ├─ [C] Fake mode (nếu camera lỗi):
        │       Dùng JPEG 1×1 pixel (hardcoded)
        │       → hệ thống vẫn chạy, uploader vẫn gửi
        │
        ├─ [D] Cấp phát bản sao PSRAM:
        │       heap_caps_malloc(frame_len, MALLOC_CAP_SPIRAM)
        │       memcpy(copy, fb->buf, fb->len)
        │
        ├─ [E] Gửi vào g_frame_queue (non-blocking):
        │       xQueueSend(g_frame_queue, &msg, 0)
        │       Queue đầy → free PSRAM copy + cảnh báo
        │
        ├─ [F] Cập nhật latest frame (cho HTTP server tương lai):
        │       update_latest_frame_shared(fb->buf, fb->len)
        │
        └─ [G] esp_camera_fb_return(fb) ← trả buffer về camera
```

---

## Đổi Resolution/Quality từ ThingsBoard

Khi MQTT nhận lệnh `setResolution` hoặc shared attr `jpeg_quality`:
```
mqtt_app.c → xQueueSend(g_mqtt_cmd_queue, &cmd, ...)
                    │
camera_task vòng lặp kế tiếp → xQueuePeek()
                    │
             apply_camera_cmd():
               sensor_t *s = esp_camera_sensor_get()
               s->set_framesize(s, FRAMESIZE_SVGA)  // hoặc
               s->set_quality(s, 15)
```

**Thay đổi ngay lập tức** không cần restart — frame tiếp theo đã dùng cấu hình mới.

---

## FRAMESIZE values thường dùng

| Enum | Độ phân giải | Ghi chú |
|------|-------------|---------|
| `FRAMESIZE_QVGA` | 320×240 | Nhỏ nhất, nhanh nhất |
| `FRAMESIZE_VGA` | 640×480 | **Mặc định** — tốt cho nhận diện |
| `FRAMESIZE_SVGA` | 800×600 | Tốt hơn nhưng chậm hơn |
| `FRAMESIZE_XGA` | 1024×768 | Cần PSRAM |
| `FRAMESIZE_SXGA` | 1280×1024 | Cần PSRAM, chậm |
| `FRAMESIZE_UXGA` | 1600×1200 | Tối đa, rất chậm |

---

## Timing & Throughput

| Tham số | Giá trị mặc định | Thay đổi qua |
|---------|-----------------|--------------|
| Capture interval | 1000ms (1 fps) | RPC `setInterval` / Shared attr `capture_interval` |
| JPEG quality | 10 | RPC `setQuality` / Shared attr `jpeg_quality` |
| Framesize | FRAMESIZE_VGA | RPC `setResolution` / Shared attr `resolution` |

Ước tính kích thước JPEG VGA quality=10: **15–40 KB/frame**.

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/camera_task.c` | FreeRTOS task chụp ảnh |
| `src/goouuu_camera.c` | `goouuu_camera_config_default()` |
| `include/goouuu_board.h` | Pin map + CAM_PIN_* aliases |
| `include/goouuu_camera.h` | Header config camera |
| `include/task_common.h` | `frame_msg_t`, `CAMERA_TASK_STACK_SIZE` |
