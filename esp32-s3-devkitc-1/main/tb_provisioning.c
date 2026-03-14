/*
 * tb_provisioning.c - Provision device on ThingsBoard and store token.
 */
#include "tb_provisioning.h"

#include <string.h>

#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_mac.h"

static const char *TAG = "tb_prov";

static bool parse_token(const char *resp, char *out, size_t out_len)
{
    if (!resp || !out || out_len == 0) {
        return false;
    }

    const char *keys[] = { "credentialsValue", "accessToken" };
    for (size_t k = 0; k < sizeof(keys) / sizeof(keys[0]); k++) {
        const char *p = strstr(resp, keys[k]);
        if (!p) {
            continue;
        }
        p = strchr(p, ':');
        if (!p) {
            continue;
        }
        while (*p && (*p == ':' || *p == ' ' || *p == '"')) {
            p++;
        }

        const char *end = p;
        while (*end && *end != '"' && *end != '\n') {
            end++;
        }

        size_t len = (size_t)(end - p);
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
    return cfg &&
           cfg->provisioning_key[0] != '\0' &&
           cfg->provisioning_secret[0] != '\0';
}

bool tb_has_token(const app_config_t *cfg)
{
    return cfg && cfg->token[0] != '\0';
}

bool tb_provision_device(app_config_t *cfg)
{
    if (!cfg) {
        ESP_LOGE(TAG, "PROV | null config");
        return false;
    }
    if (!tb_has_prov_credentials(cfg)) {
        ESP_LOGE(TAG, "PROV | missing credentials");
        return false;
    }

    uint8_t mac[6] = {0};
    char dev_name[48] = "cam-unknown";
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        snprintf(
            dev_name,
            sizeof(dev_name),
            "cam-%02X%02X%02X%02X%02X%02X",
            mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
        );
    }

    char body[300];
    int body_len = snprintf(
        body,
        sizeof(body),
        "{\"deviceName\":\"%s\","
        "\"provisionDeviceKey\":\"%s\","
        "\"provisionDeviceSecret\":\"%s\","
        "\"credentialsType\":\"ACCESS_TOKEN\"}",
        dev_name,
        cfg->provisioning_key,
        cfg->provisioning_secret
    );
    if (body_len <= 0 || body_len >= (int)sizeof(body)) {
        ESP_LOGE(TAG, "PROV | request too large");
        return false;
    }

    esp_http_client_config_t http_cfg = {
        .url = TB_PROVISION_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 15000,
    };
    if (strncmp(TB_PROVISION_URL, "https", 5) == 0) {
        http_cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }

    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        ESP_LOGE(TAG, "PROV | http init failed");
        return false;
    }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, body_len);

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    int content_len = esp_http_client_get_content_length(client);

    char resp[1024] = {0};
    int total = 0;
    if (err == ESP_OK && content_len != 0) {
        int r = esp_http_client_read_response(client, resp, sizeof(resp) - 1);
        if (r > 0) {
            total = r;
            resp[total] = '\0';
        }
    }

    esp_http_client_cleanup(client);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "PROV | http error %s", esp_err_to_name(err));
        return false;
    }
    if (status != 200) {
        ESP_LOGE(TAG, "PROV | http=%d", status);
        return false;
    }
    if (total == 0 || !parse_token(resp, cfg->token, sizeof(cfg->token))) {
        ESP_LOGE(TAG, "PROV | token parse failed");
        return false;
    }

    if (app_config_save(cfg) != ESP_OK) {
        ESP_LOGW(TAG, "PROV | token in RAM only");
    }

    ESP_LOGI(TAG, "PROV | ok http=200");
    return true;
}
