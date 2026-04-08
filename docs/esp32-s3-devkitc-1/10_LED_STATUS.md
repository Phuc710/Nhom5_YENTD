# 10 - LED Status

## Phần cứng

Board dùng LED WS2812B tại `GPIO 48`.

## API

```c
led_status_init();
led_status_set_rgb(r, g, b);
led_status_off();
led_status_red();
led_status_amber();
led_status_green();
led_status_blue();
led_status_white();
```

## Mapping màu hiện tại theo code

- đỏ: lỗi / boot / mất WiFi / factory reset
- vàng: đang kết nối WiFi
- xanh lá: WiFi OK / sẵn sàng
- xanh dương: trạng thái phụ / bảo trì
- trắng: trạng thái phụ cường độ cao

## Flow hiện dùng rõ nhất

Theo `main.c`:

- boot: đỏ
- đang kết nối WiFi: vàng
- WiFi OK và runtime sẵn sàng: xanh lá

Theo `button_task.c`:

- giữ nút reset: đỏ nhấp nháy
- xác nhận reset: đỏ nhấp nhanh 5 lần

## Source of truth

- [led_status.c](../../esp32-s3-devkitc-1/main/led_status.c)
- [main.c](../../esp32-s3-devkitc-1/main/main.c)
- [button_task.c](../../esp32-s3-devkitc-1/main/button_task.c)
