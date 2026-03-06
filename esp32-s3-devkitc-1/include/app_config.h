#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

/* Phiên bản schema NVS - tăng khi thêm trường mới */
#define APP_CONFIG_MAGIC   0xA5
#define APP_CONFIG_VERSION 2

#define APP_CONFIG_DEFAULT_FRAMES_PER_UPLOAD 5
#define APP_CONFIG_MAX_FRAMES_PER_UPLOAD     10000

/** Cấu hình thiết bị lưu trong NVS */
typedef struct __attribute__((packed)) {
    uint8_t  magic;              // APP_CONFIG_MAGIC khi hợp lệ
    uint8_t  version;            // Phiên bản schema
    char     ssid[33];           // SSID WiFi
    char     password[65];       // Mật khẩu WiFi
    char     token[97];          // ThingsBoard access token
    char     prov_key[65];       // Provisioning key
    char     prov_secret[65];    // Provisioning secret
    uint16_t frames_per_upload;  // Số frame upload tối đa mỗi phiên
    uint8_t  reserved[6];
} app_config_t;

/** Trạng thái config NVS */
typedef enum {
    APP_CONFIG_STATE_EMPTY = 0,   // Chưa có config hoặc magic sai
    APP_CONFIG_STATE_VALID,       // Hợp lệ, đúng version
    APP_CONFIG_STATE_MIGRATE,     // Cần migrate (version cũ/mới)
} app_config_state_t;

/** Đặt giá trị mặc định (xóa nội dung, set magic = 0) */
void app_config_set_defaults(app_config_t *cfg);

/** Đọc config từ NVS */
esp_err_t app_config_load(app_config_t *out, app_config_state_t *state);

/** Lưu config vào NVS (ghi magic + version) */
esp_err_t app_config_save(const app_config_t *cfg);

/** Xóa config khỏi NVS (factory reset) */
esp_err_t app_config_clear(void);
