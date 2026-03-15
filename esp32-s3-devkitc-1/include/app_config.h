#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

/* Phien ban schema NVS */
#define APP_CONFIG_MAGIC   0xA5
#define APP_CONFIG_VERSION 2

/** Cau hinh thiet bi luu trong NVS */
typedef struct __attribute__((packed)) {
    uint8_t  magic;                   // APP_CONFIG_MAGIC khi hop le
    uint8_t  version;                 // Phien ban schema
    char     ssid[33];                // SSID WiFi
    char     password[65];            // Mat khau WiFi
    char     token[97];               // ThingsBoard access token
    char     provisioning_key[65];    // ThingsBoard provisioning key
    char     provisioning_secret[65]; // ThingsBoard provisioning secret
    char     location[65];            // Vị trí lắp đặt (ví dụ: Kho A, Cửa 1)
    char     device_name[33];         // Tên thiết bị (phiên bản rút gọn hoặc random)
    int32_t  camera_id;               // ID Camera
    uint8_t  backend_synced;          // 1: Đã đồng bộ backend, 0: Chưa đồng bộ
} app_config_t;

/** Trang thai config NVS */
typedef enum {
    APP_CONFIG_STATE_EMPTY = 0,
    APP_CONFIG_STATE_VALID,
    APP_CONFIG_STATE_MIGRATE,
} app_config_state_t;

/** Dat gia tri mac dinh (xoa noi dung, set magic = 0) */
void app_config_set_defaults(app_config_t *cfg);

/** Doc config tu NVS */
esp_err_t app_config_load(app_config_t *out, app_config_state_t *state);

/** Luu config vao NVS (ghi magic + version) */
esp_err_t app_config_save(const app_config_t *cfg);

/** Xoa config khoi NVS (factory reset) */
esp_err_t app_config_clear(void);

/** Xoa access token cu nhung giu WiFi + provisioning credentials */
esp_err_t app_config_clear_token(void);
