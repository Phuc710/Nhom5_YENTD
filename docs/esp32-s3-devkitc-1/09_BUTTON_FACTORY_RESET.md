# 09 — Button Task (Factory Reset)

## Tổng quan

`button_task` theo dõi nút **BOOT** (GPIO 0) để thực hiện **factory reset** khi người dùng giữ nút lâu. Đây là cơ chế khôi phục phần cứng khi thiết bị bị lỗi config hoặc mất kết nối hoàn toàn.

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

---

## Sau factory reset

1. NVS bị xóa: SSID, password, token, prov_key, prov_secret đều mất
2. Boot lại: `app_config_load()` → state `EMPTY`
3. Cần nhập lại credentials hoặc flash firmware mới
4. Nếu có `DEFAULT_WIFI_SSID` trong build flags → WiFi vẫn kết nối được
5. Provisioning chạy lại nếu có prov_key trong build flags

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/button_task.c` | Logic nút bấm |
| `include/goouuu_board.h` | `GOOUUU_GPIO_BOOT = 0` |
| `src/app_config.c` | `app_config_clear()` |
