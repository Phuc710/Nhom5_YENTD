/*
 * tb_provisioning.c — Đăng ký thiết bị lên ThingsBoard và lấy access token
 *
 * Flow:
 *   1. Đọc MAC address → tạo tên thiết bị cam-XXXXXXXXXXXX
 *   2. POST lên /api/v1/provision với prov_key + prov_secret
 *   3. Parse "credentialsValue" từ JSON response
 *   4. Lưu token vào NVS qua app_config_save()
 */
#include "tb_provisioning.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include <string.h>

static const char *TAG = "tb_prov";

/* Parse JSON thủ công (không phụ thuộc cJSON để tiết kiệm RAM) */
static bool parse_token(const char *resp, char *out, size_t out_len)
{
    if (!resp || !out || out_len == 0) return false;

    const char *keys[] = { "credentialsValue", "accessToken" };
    for (size_t k = 0; k < sizeof(keys) / sizeof(keys[0]); k++) {
        const char *p = strstr(resp, keys[k]);
        if (!p) continue;
        p = strchr(p, ':');
        if (!p) continue;
        while (*p && (*p == ':' || *p == ' ' || *p == '"')) p++;
        const char *end = p;
        while (*end && *end != '"' && *end != '\n') end++;
        size_t len = end - p;
        if (len > 0 && len < out_len) {
            memcpy(out, p, len);
            out[len] = '\0';
            return true;
        }
    }
    return false;
}

bool tb_has_prov_credentials(const app_config_t *cfg)
{
    return cfg && cfg->prov_key[0] != '\0' && cfg->prov_secret[0] != '\0';
}

bool tb_has_token(const app_config_t *cfg)
{
    return cfg && cfg->token[0] != '\0';
}

bool tb_provision_device(app_config_t *cfg)
{
    if (!cfg) {
        ESP_LOGE(TAG, "Config NULL");
        return false;
    }
    if (!tb_has_prov_credentials(cfg)) {
        ESP_LOGE(TAG, "Chưa có provisioning credentials");
        return false;
    }

    /* Tên thiết bị từ MAC */
    char dev_name[48];
    uint8_t mac[6] = {0};
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) != ESP_OK) {
        snprintf(dev_name, sizeof(dev_name), "cam-unknown");
    } else {
        snprintf(dev_name, sizeof(dev_name),
                 "cam-%02X%02X%02X%02X%02X%02X",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }

    /* JSON body */
    char body[300];
    int body_len = snprintf(body, sizeof(body),
        "{\"deviceName\":\"%s\","
        "\"provisionDeviceKey\":\"%s\","
        "\"provisionDeviceSecret\":\"%s\","
        "\"credentialsType\":\"ACCESS_TOKEN\"}",
        dev_name, cfg->prov_key, cfg->prov_secret);

    if (body_len <= 0 || body_len >= (int)sizeof(body)) {
        ESP_LOGE(TAG, "Body quá dài");
        return false;
    }

    ESP_LOGI(TAG, "=== PROVISIONING ===");
    ESP_LOGI(TAG, "Tên thiết bị: %s", dev_name);
    ESP_LOGI(TAG, "URL: %s", TB_PROVISION_URL);

    esp_http_client_config_t http_cfg = {
        .url         = TB_PROVISION_URL,
        .method      = HTTP_METHOD_POST,
        .timeout_ms  = 15000,
    };
    /* Gắn TLS bundle nếu URL là HTTPS */
    if (strncmp(TB_PROVISION_URL, "https", 5) == 0) {
        http_cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }

    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        ESP_LOGE(TAG, "HTTP client init thất bại");
        return false;
    }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, body_len);

    /* Mở kết nối và gửi */
    if (esp_http_client_open(client, body_len) != ESP_OK) {
        ESP_LOGE(TAG, "Mở kết nối HTTP thất bại");
        esp_http_client_cleanup(client);
        return false;
    }
    if (esp_http_client_write(client, body, body_len) < 0) {
        ESP_LOGE(TAG, "Ghi HTTP request thất bại");
        esp_http_client_cleanup(client);
        return false;
    }

    esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    ESP_LOGI(TAG, "HTTP status: %d", status);

    /* Đọc response */
    char resp[1024] = {0};
    int total = 0;
    while (total < (int)sizeof(resp) - 1) {
        int r = esp_http_client_read(client, resp + total,
                                     sizeof(resp) - 1 - total);
        if (r <= 0) break;
        total += r;
    }
    resp[total] = '\0';
    esp_http_client_cleanup(client);

    if (status != 200 || total == 0) {
        ESP_LOGE(TAG, "Provisioning thất bại (status=%d)", status);
        return false;
    }

    if (!parse_token(resp, cfg->token, sizeof(cfg->token))) {
        ESP_LOGE(TAG, "Không parse được token từ response");
        return false;
    }

    ESP_LOGI(TAG, "Provisioning thành công! Token: %.10s...", cfg->token);

    /* Lưu token vào NVS */
    if (app_config_save(cfg) != ESP_OK) {
        ESP_LOGW(TAG, "Lưu config NVS thất bại (token vẫn hoạt động trong RAM)");
    }
    return true;
}
