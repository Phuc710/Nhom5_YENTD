# 10 — LED Status (WS2812 RGB)

## Tổng quan

Board GOOUUU N16R8 có **1 đèn LED WS2812B** tích hợp tại **GPIO 48**.  
Firmware dùng LED để phản hồi trạng thái hệ thống real-time — không cần kết nối Serial Monitor.

---

## Hardware

| Component | Chi tiết |
|-----------|---------|
| GPIO | GPIO 48 (`GOOUUU_GPIO_RGB`) |
| Protocol | WS2812B (single-wire NRZ) |
| Interface | ESP-IDF RMT TX, 10 MHz resolution |
| Màu | GRB order (Green-Red-Blue) |

---

## Timing WS2812B

```
Bit 0: ▔▔█    T0H=0.40µs + T0L=0.85µs
Bit 1: ▔▔▔▔▔█ T1H=0.85µs + T1L=0.45µs
Reset: LOW ≥ 50µs
```
Được implement trong `led_strip_encoder.c` dùng `rmt_new_bytes_encoder`.

---

## API

```c
led_status_init();              // Khởi tạo RMT (tự gọi lại nếu chưa init)
led_status_set_rgb(r, g, b);    // Đặt màu (0–255 mỗi kênh)
led_status_off();               // Tắt LED = (0,0,0)
led_status_white();             // Trắng = (32,32,32)  ← dùng 32 để không chói
```

---

## Bảng trạng thái màu

| Màu | RGB | Trạng thái |
|-----|-----|-----------|
| ⚪ Trắng mờ | `(8,8,8)` | Đang boot |
| 🟡 Vàng nhạt | `(32,24,0)` | Đang kết nối WiFi |
| 🟢 Xanh lá | `(0,48,0)` | WiFi thành công |
| 🔴 Đỏ | `(48,0,0)` | WiFi thất bại / Lỗi nghiêm trọng |
| 🩵 Cyan | `(0,32,32)` | Đang provisioning ThingsBoard |
| 🟠 Cam | `(48,24,0)` | Provisioning thất bại (cảnh báo) |
| 🔵 Xanh dương | `(0,0,64)` | Đang OTA download |
| 🟢 Xanh lá OTA | `(0,64,0)` | OTA thành công |
| 🔴 Đỏ OTA | `(64,0,0)` | OTA thất bại |
| 🔵 Xanh nhạt | `(0,16,32)` | Đang khởi động tasks |
| ⚪ Trắng đầy | `(32,32,32)` | Hệ thống chạy bình thường |
| 🔴↔⚫ Nháy đỏ | `(48,0,0)↔(0,0,0)` | Upload thất bại liên tục |
| 🔴 Nháy 3 lần | `(64,0,0)×3` | Factory Reset sắp xảy ra |

---

## Flow RMT trong led_status.c

```
led_status_set_rgb(r, g, b)
        │
        ▼
uint8_t grb[3] = { g, r, b }  // WS2812 nhận GRB, không phải RGB!
        │
        ▼
rmt_transmit(s_chan, s_enc, grb, 3, &s_tx)
        │
        ▼
rmt_tx_wait_all_done(s_chan, 100ms)
```

**Lưu ý: WS2812 nhận byte theo thứ tự GRB** — firmware tự hoán đổi.

---

## Khởi tạo RMT

```c
// Tần số 10 MHz = mỗi tick 100ns
rmt_tx_channel_config_t tx_cfg = {
    .gpio_num         = GOOUUU_GPIO_RGB,   // GPIO 48
    .resolution_hz    = 10*1000*1000,       // 10 MHz
    .mem_block_symbols= 64,
    .trans_queue_depth= 4,
};
rmt_new_tx_channel(&tx_cfg, &s_chan);

led_strip_encoder_config_t enc_cfg = { .resolution = 10000000 };
rmt_new_led_strip_encoder(&enc_cfg, &s_enc);
rmt_enable(s_chan);
```

---

## Mở rộng: Nhiều LED

Nếu thêm LED strip (nhiều LED NeoPixel), sửa `led_status.c`:
```c
uint8_t grb[3 * NUM_LEDS];
// Điền màu cho từng LED
rmt_transmit(s_chan, s_enc, grb, sizeof(grb), &s_tx);
```

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/led_status.c` | Driver LED — API public |
| `include/led_status.h` | API declaration |
| `src/led_strip_encoder.c` | WS2812 RMT timing encoder |
| `include/led_strip_encoder.h` | Encoder config |
| `include/goouuu_board.h` | `GOOUUU_GPIO_RGB = 48` |
