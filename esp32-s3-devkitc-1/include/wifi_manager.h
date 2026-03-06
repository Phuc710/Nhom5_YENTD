#pragma once

#include <stdbool.h>

void wifi_manager_init(void);
bool wifi_connect_with_retry(const char *ssid, const char *password, int max_retry);
