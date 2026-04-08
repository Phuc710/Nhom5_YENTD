/*
 * app_config.c — Quản lý cấu hình thiết bị qua NVS
 */
#include "app_config.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include <string.h>

static const char *TAG = "app_config";
#define NVS_NAMESPACE "app_cfg"
#define NVS_KEY       "config"

void app_config_set_defaults(app_config_t *cfg)
{
    if (!cfg) return;
    memset(cfg, 0, sizeof(*cfg));
    cfg->version = APP_CONFIG_VERSION;
#ifdef DEFAULT_DEVICE_LOCATION
    strncpy(cfg->location, DEFAULT_DEVICE_LOCATION, sizeof(cfg->location) - 1);
#else
    strncpy(cfg->location, "Chưa xác định", sizeof(cfg->location) - 1);
#endif

#ifdef DEFAULT_CAMERA_ID
    cfg->camera_id = DEFAULT_CAMERA_ID;
#else
    cfg->camera_id = 1;
#endif
    cfg->device_name[0] = '\0';
    cfg->backend_synced = 0;
}

esp_err_t app_config_load(app_config_t *out, app_config_state_t *state)
{
    if (!out || !state) return ESP_ERR_INVALID_ARG;

    app_config_set_defaults(out);
    *state = APP_CONFIG_STATE_EMPTY;

    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "CFG | Chưa có cấu hình trong NVS");
        return ESP_OK;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CFG | Mở NVS thất bại: %s", esp_err_to_name(err));
        return err;
    }

    size_t len = sizeof(*out);
    err = nvs_get_blob(h, NVS_KEY, out, &len);
    nvs_close(h);

    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "CFG | Chưa có key config");
        app_config_set_defaults(out);
        return ESP_OK;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CFG | Đọc NVS thất bại: %s", esp_err_to_name(err));
        app_config_set_defaults(out);
        return err;
    }

    if (out->magic != APP_CONFIG_MAGIC) {
        ESP_LOGW(TAG, "CFG | Magic byte sai (0x%02X), reset config", out->magic);
        app_config_set_defaults(out);
        *state = APP_CONFIG_STATE_EMPTY;
        return ESP_OK;
    }

    if (out->version != APP_CONFIG_VERSION) {
        ESP_LOGW(TAG, "CFG | Version config không khớp (%d -> %d), tự động xóa để tránh lỗi cấu trúc",
                 out->version, APP_CONFIG_VERSION);
        app_config_set_defaults(out);
        *state = APP_CONFIG_STATE_EMPTY;
    } else {
        *state = APP_CONFIG_STATE_VALID;
    }

    ESP_LOGI(TAG, "CFG | Đọc thành công | SSID: %s | Device: %s | Vị trí: %s",
             out->ssid,
             out->device_name[0] ? out->device_name : "(trống)",
             out->location);
    return ESP_OK;
}

esp_err_t app_config_save(const app_config_t *cfg)
{
    if (!cfg) return ESP_ERR_INVALID_ARG;

    /* Tạo bản sao có magic + version đúng */
    app_config_t tmp = *cfg;
    tmp.magic   = APP_CONFIG_MAGIC;
    tmp.version = APP_CONFIG_VERSION;

    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CFG | Mở NVS ghi thất bại: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_set_blob(h, NVS_KEY, &tmp, sizeof(tmp));
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CFG | Lưu cấu hình thất bại: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "CFG | Đã lưu cấu hình vào NVS");
    }
    return err;
}

esp_err_t app_config_clear(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    err = nvs_erase_all(h);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);

    ESP_LOGW(TAG, "CFG | Đã xóa toàn bộ config (Factory Reset)");
    return err;
}

esp_err_t app_config_clear_token(void)
{
    app_config_t cfg;
    app_config_state_t state;
    esp_err_t err = app_config_load(&cfg, &state);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CFG | Không thể đọc cấu hình để xóa token: %s", esp_err_to_name(err));
        return err;
    }

    if (state == APP_CONFIG_STATE_EMPTY) {
        ESP_LOGW(TAG, "Chưa có config trong NVS, không cần xóa token");
        return ESP_OK;
    }

    if (cfg.token[0] == '\0' && cfg.backend_synced == 0) {
        ESP_LOGI(TAG, "CFG | Token đã trống sẵn, bỏ qua");
        return ESP_OK;
    }

    cfg.token[0] = '\0';
    cfg.backend_synced = 0; // Reset trạng thái đồng bộ khi xóa token
    err = app_config_save(&cfg);
    if (err == ESP_OK) {
        ESP_LOGW(TAG, "CFG | Đã xóa token cũ, sẽ provision lại khi reboot");
    }

    return err;
}
