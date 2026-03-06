#pragma once

#include <stdint.h>

void led_status_init(void);
void led_status_set_rgb(uint8_t r, uint8_t g, uint8_t b);
void led_status_off(void);
void led_status_white(void);
