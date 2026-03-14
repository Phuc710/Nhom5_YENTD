#pragma once

#include <stdint.h>

/*
 * led_status.h — Trạng thái LED RGB WS2812B (GPIO 48)
 *
 * Quy ước 1 trạng thái = 1 màu:
 *   🔴 Đỏ     → Lỗi / Chưa có WiFi / Boot khởi tạo
 *   🟡 Vàng   → Đang kết nối WiFi / Đang xử lý
 *   🟢 Xanh lá → WiFi đã kết nối thành công / Sẵn sàng
 *   🔵 Xanh lam → Trạng thái phụ / bảo trì
 *   ⚪ Trắng  → Camera đang hoạt động mạnh
 *   ○  Tắt    → Tắt hoàn toàn (không dùng bình thường)
 */

void led_status_init(void);
void led_status_set_rgb(uint8_t r, uint8_t g, uint8_t b);

void led_status_off(void);       /* Tắt LED */
void led_status_red(void);       /* 🔴 Lỗi / Boot / Mất WiFi */
void led_status_amber(void);     /* 🟡 Đang kết nối WiFi */
void led_status_green(void);     /* 🟢 WiFi OK / Hoàn tất */
void led_status_blue(void);      /* 🔵 Trạng thái phụ / bảo trì */
void led_status_white(void);     /* ⚪ Camera đang hoạt động mạnh */
