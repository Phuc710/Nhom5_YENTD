/*
 * led_status.c — Điều khiển đèn LED RGB WS2812 (GPIO 48) qua RMT
 */
#include "led_status.h"
#include "goouuu_board.h"
#include "led_strip_encoder.h"
#include "driver/rmt_tx.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "led_status";

static rmt_channel_handle_t s_chan    = NULL;
static rmt_encoder_handle_t s_enc    = NULL;
static rmt_transmit_config_t s_tx    = { .loop_count = 0 };
static bool s_ready = false;

void led_status_init(void)
{
    if (s_ready) return;

    const uint32_t resolution = 10 * 1000 * 1000; // 10 MHz

    rmt_tx_channel_config_t tx_cfg = {
        .clk_src          = RMT_CLK_SRC_DEFAULT,
        .gpio_num         = GOOUUU_GPIO_RGB,
        .mem_block_symbols= 64,
        .resolution_hz    = resolution,
        .trans_queue_depth= 4,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&tx_cfg, &s_chan));

    led_strip_encoder_config_t enc_cfg = { .resolution = resolution };
    ESP_ERROR_CHECK(rmt_new_led_strip_encoder(&enc_cfg, &s_enc));
    ESP_ERROR_CHECK(rmt_enable(s_chan));

    s_ready = true;
    ESP_LOGI(TAG, "LED RGB đã khởi tạo (GPIO %d)", GOOUUU_GPIO_RGB);
}

void led_status_set_rgb(uint8_t r, uint8_t g, uint8_t b)
{
    if (!s_ready) led_status_init();

    uint8_t grb[3] = { g, r, b }; // WS2812 nhận GRB
    esp_err_t err = rmt_transmit(s_chan, s_enc, grb, sizeof(grb), &s_tx);
    if (err == ESP_OK) {
        rmt_tx_wait_all_done(s_chan, pdMS_TO_TICKS(100));
    } else {
        ESP_LOGW(TAG, "Gửi LED thất bại: %s", esp_err_to_name(err));
    }
}

void led_status_off(void)   { led_status_set_rgb(0,  0,  0);  }
void led_status_white(void) { led_status_set_rgb(32, 32, 32); }
