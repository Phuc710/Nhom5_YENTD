/*
 * led_strip_encoder.h — RMT encoder cho WS2812 (NeoPixel)
 */
#pragma once

#include "driver/rmt_encoder.h"

typedef struct {
    uint32_t resolution;  // Tần số RMT (Hz), thường là 10MHz
} led_strip_encoder_config_t;

/** Tạo RMT encoder cho WS2812 */
esp_err_t rmt_new_led_strip_encoder(const led_strip_encoder_config_t *config,
                                    rmt_encoder_handle_t *ret_encoder);
