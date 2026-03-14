/*
 * led_status.c — Điều khiển LED RGB WS2812B (GPIO 48) qua RMT
 *
 * Quy ước 1 trạng thái = 1 màu:
 *   🔴 Đỏ     → Lỗi / Chưa có WiFi / Boot khởi tạo
 *   🟡 Vàng   → Đang kết nối WiFi / Đang xử lý
 *   🟢 Xanh lá → WiFi đã kết nối thành công / Sẵn sàng
 *   🔵 Xanh lam → Trạng thái phụ / bảo trì
 *   ⚪ Trắng  → Camera đang hoạt động mạnh
 */
#include "led_status.h"
#include "goouuu_board.h"
#include "led_strip_encoder.h"
#include "driver/rmt_tx.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "led";

/* Mức sáng mặc định (0–255). WS2812B ở 80/255 ≈ 31% — đủ nhìn, không chói */
#define LED_LEVEL 80

static rmt_channel_handle_t s_chan = NULL;
static rmt_encoder_handle_t s_enc  = NULL;
static rmt_transmit_config_t s_tx  = { .loop_count = 0 };
static bool s_ready = false;

void led_status_init(void)
{
    if (s_ready) return;

    const uint32_t resolution = 10 * 1000 * 1000; /* 10 MHz */

    rmt_tx_channel_config_t tx_cfg = {
        .clk_src           = RMT_CLK_SRC_DEFAULT,
        .gpio_num          = GOOUUU_GPIO_RGB,
        .mem_block_symbols = 64,
        .resolution_hz     = resolution,
        .trans_queue_depth = 4,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&tx_cfg, &s_chan));

    led_strip_encoder_config_t enc_cfg = { .resolution = resolution };
    ESP_ERROR_CHECK(rmt_new_led_strip_encoder(&enc_cfg, &s_enc));
    ESP_ERROR_CHECK(rmt_enable(s_chan));

    s_ready = true;
    ESP_LOGI(TAG, "💡 LED: Khởi tạo thành công (GPIO %d, mức sáng %d/255)", GOOUUU_GPIO_RGB, LED_LEVEL);
}

void led_status_set_rgb(uint8_t r, uint8_t g, uint8_t b)
{
    if (!s_ready) led_status_init();

    uint8_t grb[3] = { g, r, b }; /* WS2812B nhận thứ tự GRB */
    esp_err_t err = rmt_transmit(s_chan, s_enc, grb, sizeof(grb), &s_tx);
    if (err == ESP_OK) {
        rmt_tx_wait_all_done(s_chan, pdMS_TO_TICKS(100));
    } else {
        ESP_LOGW(TAG, "⚠️ LED: Không thể gửi dữ liệu (%s)", esp_err_to_name(err));
    }
}

/* 🔴 Lỗi / Boot / Mất WiFi / Factory reset */
void led_status_red(void)   { led_status_set_rgb(LED_LEVEL, 0, 0); }

/* 🟡 Đang kết nối WiFi */
void led_status_amber(void) { led_status_set_rgb(LED_LEVEL, LED_LEVEL / 3, 0); }

/* 🟢 WiFi đã kết nối / Hoàn tất khởi động */
void led_status_green(void) { led_status_set_rgb(0, LED_LEVEL, 0); }

/* 🔵 Trạng thái phụ / bảo trì */
void led_status_blue(void)  { led_status_set_rgb(0, 0, LED_LEVEL); }

/* ⚪ Camera đang hoạt động mạnh */
void led_status_white(void) { led_status_set_rgb(LED_LEVEL, LED_LEVEL, LED_LEVEL); }

/* Tắt LED hoàn toàn */
void led_status_off(void)   { led_status_set_rgb(0, 0, 0); }
