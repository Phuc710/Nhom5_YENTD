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
    cfg->frames_per_upload = APP_CONFIG_DEFAULT_FRAMES_PER_UPLOAD;
}

esp_err_t app_config_load(app_config_t *out, app_config_state_t *state)
{
    if (!out || !state) return ESP_ERR_INVALID_ARG;

    app_config_set_defaults(out);
    *state = APP_CONFIG_STATE_EMPTY;

    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "Chưa có config trong NVS");
        return ESP_OK;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Mở NVS thất bại: %s", esp_err_to_name(err));
        return err;
    }

    size_t len = sizeof(*out);
    err = nvs_get_blob(h, NVS_KEY, out, &len);
    nvs_close(h);

    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "Chưa có key config");
        app_config_set_defaults(out);
        return ESP_OK;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Đọc NVS thất bại: %s", esp_err_to_name(err));
        app_config_set_defaults(out);
        return err;
    }

    if (out->magic != APP_CONFIG_MAGIC) {
        ESP_LOGW(TAG, "Magic byte sai (0x%02X), reset config", out->magic);
        app_config_set_defaults(out);
        *state = APP_CONFIG_STATE_EMPTY;
        return ESP_OK;
    }

    if (out->version != APP_CONFIG_VERSION) {
        ESP_LOGW(TAG, "Version config cũ (%d → %d), cần migrate",
                 out->version, APP_CONFIG_VERSION);
        *state = APP_CONFIG_STATE_MIGRATE;
    } else {
        *state = APP_CONFIG_STATE_VALID;
    }

    ESP_LOGI(TAG, "Đọc config thành công | SSID: %s | Token: %s",
             out->ssid,
             out->token[0] ? "(có)" : "(trống)");
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
        ESP_LOGE(TAG, "Mở NVS ghi thất bại: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_set_blob(h, NVS_KEY, &tmp, sizeof(tmp));
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Lưu config thất bại: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Config đã lưu vào NVS");
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

    ESP_LOGW(TAG, "Đã xóa toàn bộ config (factory reset)");
    return err;
}
