#pragma once

#include "esp_err.h"

/** Khởi động HTTP server local của ESP32 để test stream/snapshot. */
esp_err_t stream_server_start(void);

/** Dừng HTTP server local. */
void stream_server_stop(void);
