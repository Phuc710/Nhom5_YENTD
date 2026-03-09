# 09 — Button Task (Factory Reset)

## Tổng quan

`button_task` theo dõi nút **BOOT** (GPIO 0) để thực hiện **factory reset** khi người dùng giữ nút lâu. Đây là cơ chế khôi phục phần cứng khi thiết bị bị lỗi config hoặc mất kết nối hoàn toàn.

Lưu ý:

- nhấn `RESET/EN` trên board chỉ là **reboot**
- giữ nút `BOOT` lâu mới là **factory reset**
- `reprovision` qua ThingsBoard chỉ xóa token, không xóa sạch NVS

---

## Hardware

| Component | Chi tiết |
|-----------|---------|
| GPIO | GPIO 0 (GOOUUU_GPIO_BOOT) |
| Điện trở | Pull-up nội (GPIO_PULLUP_ENABLE) |
| Mức logic | HIGH = không nhấn, LOW = đang nhấn |
| Nút | Nút BOOT có sẵn trên board |

---

## Flow `button_task`

```
button_task() khởi động
  gpio_config:
    GPIO 0, INPUT, PULL_UP, INTR_DISABLE
        │
        ▼
Vòng lặp (mỗi DEBOUNCE_MS = 50ms):
  │
  ├─ Đọc GPIO 0 level
  │
  ├─ Falling edge (HIGH→LOW) = nút vừa nhấn:
  │   press_start = tick hiện tại
  │   long_handled = false
  │
  ├─ Đang giữ (LOW + !long_handled):
  │   held_ms = (tick_now - press_start) * 10ms
  │   held_ms >= 3000ms?
  │     YES:
  │       long_handled = true
  │       Log: "Giữ nút 3000ms → Factory Reset!"
  │       LED nháy đỏ 3 lần (mỗi lần 150ms ON + 150ms OFF)
  │       app_config_clear()   ← Xóa toàn bộ NVS
  │       vTaskDelay(500ms)
  │       esp_restart()         ← Reboot
  │
  └─ Rising edge (LOW→HIGH) = nút nhả:
      Log: "Nút nhả sau X ms"
      (nhấn nhanh < 3s không làm gì)
```

---

## LED feedback khi factory reset

```
Nhấn giữ 3s:
  ┌──── 150ms ────┐ ┌──── 150ms ────┐ ┌──── 150ms ────┐
  │  Đỏ (64,0,0)  │ │  Tắt (0,0,0)  │ │  Đỏ (64,0,0)  │ ...×3
  └───────────────┘ └───────────────┘ └───────────────┘
                                                   │
                                             esp_restart()
```

---

## Các cách Factory Reset khác

| Phương pháp | Cách thực hiện |
|------------|----------------|
| **Nút BOOT** | Giữ > 3 giây |
| **ThingsBoard RPC** | `factoryReset` |
| **ThingsBoard Shared Attr** | `factory_reset = true` hoặc `reset = true` |

## Provision lại mà không xóa sạch NVS

Khi chỉ muốn xin token mới:

- RPC: `reprovision`
- Shared attribute: `reprovision = true`
- Shared attribute tương thích: `clear_token = true`

Firmware sẽ `app_config_clear_token()` rồi reboot. WiFi và provisioning credentials được giữ nguyên.

---

## Sau factory reset

1. NVS bị xóa: SSID, password, token, provisioning_key, provisioning_secret đều mất
2. Boot lại: `app_config_load()` → state `EMPTY`
3. Cần nhập lại credentials hoặc flash firmware mới
4. Sau factory reset, board sẽ bật AP config để nhập lại WiFi
5. Provisioning chạy lại nếu có `provisioning_key` và `provisioning_secret` trong build flags

## Cap nhat sau factory reset

Flow moi sau `factory reset`:

1. NVS rong -> mat WiFi da luu.
2. Board khong con lay WiFi build-time de tu vao mang.
3. ESP32 bat AP config `kaishop` tai `http://192.168.4.1/`.
4. User nhap WiFi moi qua portal roi board ket noi lai.
5. Neu van con `provisioning_key` / `provisioning_secret` tu build flags thi firmware co the provision lai sau khi co mang.

Luu y: `wifi_ap_pass = 1` se tao `open AP` do SoftAP ESP-IDF yeu cau password tu 8 ky tu tro len neu dung WPA2.

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/button_task.c` | Logic nút bấm |
| `include/goouuu_board.h` | `GOOUUU_GPIO_BOOT = 0` |
| `src/app_config.c` | `app_config_clear()` |
