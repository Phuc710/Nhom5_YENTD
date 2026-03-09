/*
 * led_strip_encoder.c — RMT encoder tùy chỉnh cho WS2812 (NeoPixel)
 * Timing chuẩn WS2812B: T0H=0.4µs T0L=0.85µs T1H=0.85µs T1L=0.45µs
 */
#include "led_strip_encoder.h"
#include "esp_check.h"
#include <stdlib.h>

static const char *TAG = "ws2812_enc";

typedef struct {
    rmt_encoder_t base;
    rmt_encoder_t *bytes_encoder;
    rmt_encoder_t *copy_encoder;
    int state;
    rmt_symbol_word_t reset_code;
} rmt_led_strip_encoder_t;

static size_t rmt_encode_led_strip(
    rmt_encoder_t *encoder,
    rmt_channel_handle_t channel,
    const void *primary_data,
    size_t data_size,
    rmt_encode_state_t *ret_state
)
{
    rmt_led_strip_encoder_t *led_encoder =
        __containerof(encoder, rmt_led_strip_encoder_t, base);

    rmt_encoder_handle_t bytes_encoder = led_encoder->bytes_encoder;
    rmt_encoder_handle_t copy_encoder = led_encoder->copy_encoder;
    rmt_encode_state_t session_state = RMT_ENCODING_RESET;
    rmt_encode_state_t state = RMT_ENCODING_RESET;
    size_t encoded_syms = 0;

    switch (led_encoder->state) {
        case 0:
            encoded_syms += bytes_encoder->encode(
                bytes_encoder,
                channel,
                primary_data,
                data_size,
                &session_state
            );
            if (session_state & RMT_ENCODING_COMPLETE) {
                led_encoder->state = 1;
            }
            if (session_state & RMT_ENCODING_MEM_FULL) {
                state |= RMT_ENCODING_MEM_FULL;
                goto out;
            }
            /* fall through */
        case 1:
            encoded_syms += copy_encoder->encode(
                copy_encoder,
                channel,
                &led_encoder->reset_code,
                sizeof(led_encoder->reset_code),
                &session_state
            );
            if (session_state & RMT_ENCODING_COMPLETE) {
                led_encoder->state = RMT_ENCODING_RESET;
                state |= RMT_ENCODING_COMPLETE;
            }
            if (session_state & RMT_ENCODING_MEM_FULL) {
                state |= RMT_ENCODING_MEM_FULL;
                goto out;
            }
            break;
        default:
            break;
    }

out:
    *ret_state = state;
    return encoded_syms;
}

static esp_err_t rmt_del_led_strip_encoder(rmt_encoder_t *encoder)
{
    rmt_led_strip_encoder_t *led_encoder =
        __containerof(encoder, rmt_led_strip_encoder_t, base);
    rmt_del_encoder(led_encoder->bytes_encoder);
    rmt_del_encoder(led_encoder->copy_encoder);
    free(led_encoder);
    return ESP_OK;
}

static esp_err_t rmt_led_strip_encoder_reset(rmt_encoder_t *encoder)
{
    rmt_led_strip_encoder_t *led_encoder =
        __containerof(encoder, rmt_led_strip_encoder_t, base);
    rmt_encoder_reset(led_encoder->bytes_encoder);
    rmt_encoder_reset(led_encoder->copy_encoder);
    led_encoder->state = RMT_ENCODING_RESET;
    return ESP_OK;
}

esp_err_t rmt_new_led_strip_encoder(
    const led_strip_encoder_config_t *config,
    rmt_encoder_handle_t *ret_encoder
)
{
    ESP_RETURN_ON_FALSE(config && ret_encoder, ESP_ERR_INVALID_ARG, TAG, "Tham số không hợp lệ");

    rmt_led_strip_encoder_t *led_encoder = calloc(1, sizeof(rmt_led_strip_encoder_t));
    ESP_RETURN_ON_FALSE(led_encoder, ESP_ERR_NO_MEM, TAG, "Không đủ bộ nhớ cho encoder");

    led_encoder->base.encode = rmt_encode_led_strip;
    led_encoder->base.del = rmt_del_led_strip_encoder;
    led_encoder->base.reset = rmt_led_strip_encoder_reset;

    uint32_t res = config->resolution;
    rmt_bytes_encoder_config_t bytes_encoder_config = {
        .bit0 = {
            .level0 = 1,
            .duration0 = (uint16_t)(0.4e-6 * res),
            .level1 = 0,
            .duration1 = (uint16_t)(0.85e-6 * res),
        },
        .bit1 = {
            .level0 = 1,
            .duration0 = (uint16_t)(0.85e-6 * res),
            .level1 = 0,
            .duration1 = (uint16_t)(0.45e-6 * res),
        },
        .flags.msb_first = 1,
    };

    esp_err_t ret = rmt_new_bytes_encoder(&bytes_encoder_config, &led_encoder->bytes_encoder);
    ESP_GOTO_ON_ERROR(ret, err, TAG, "Tạo bytes encoder thất bại");

    rmt_copy_encoder_config_t copy_encoder_config = {};
    ret = rmt_new_copy_encoder(&copy_encoder_config, &led_encoder->copy_encoder);
    ESP_GOTO_ON_ERROR(ret, err, TAG, "Tạo copy encoder thất bại");

    uint32_t reset_ticks = (uint32_t)(50e-6 * res / 2);
    led_encoder->reset_code = (rmt_symbol_word_t){
        .level0 = 0,
        .duration0 = reset_ticks,
        .level1 = 0,
        .duration1 = reset_ticks,
    };

    *ret_encoder = &led_encoder->base;
    return ESP_OK;

err:
    if (led_encoder->bytes_encoder) {
        rmt_del_encoder(led_encoder->bytes_encoder);
    }
    if (led_encoder->copy_encoder) {
        rmt_del_encoder(led_encoder->copy_encoder);
    }
    free(led_encoder);
    return ret;
}
