#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "app_config.h"

void wifi_manager_init(void);
bool wifi_manager_ensure_connected(app_config_t *cfg, int max_retry);
bool wifi_manager_verify_connected_sta(void);
bool wifi_get_ip_string(char *buffer, size_t buffer_len);
