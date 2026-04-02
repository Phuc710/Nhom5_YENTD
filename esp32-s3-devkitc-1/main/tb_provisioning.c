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

typedef struct {
    char   *buf;
    size_t  cap;
    size_t  len;
    bool    truncated;
} http_resp_buf_t;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    if (!evt || evt->event_id != HTTP_EVENT_ON_DATA || !evt->user_data || !evt->data || evt->data_len <= 0) {
        return ESP_OK;
    }

    http_resp_buf_t *resp = (http_resp_buf_t *)evt->user_data;
    if (!resp->buf || resp->cap == 0 || resp->len >= resp->cap - 1) {
        resp->truncated = true;
        return ESP_OK;
    }

    size_t avail = resp->cap - resp->len - 1;
    size_t copy_len = (size_t)evt->data_len < avail ? (size_t)evt->data_len : avail;
    if (copy_len > 0) {
        memcpy(resp->buf + resp->len, evt->data, copy_len);
        resp->len += copy_len;
        resp->buf[resp->len] = '\0';
    }
    if (copy_len < (size_t)evt->data_len) {
        resp->truncated = true;
    }

    return ESP_OK;
}

static bool parse_json_string_field(const char *resp, const char *key, char *out, size_t out_len)
{
    if (!resp || !key || !out || out_len == 0) {
        return false;
    }

    const char *p = strstr(resp, key);
    if (!p) {
        return false;
    }

    p = strchr(p, ':');
    if (!p) {
        return false;
    }
    while (*p && (*p == ':' || *p == ' ' || *p == '"')) {
        p++;
    }

    const char *end = p;
    while (*end && *end != '"' && *end != '\n') {
        end++;
    }

    size_t len = (size_t)(end - p);
    if (len == 0 || len >= out_len) {
        return false;
    }

    memcpy(out, p, len);
    out[len] = '\0';
    return true;
}

static bool parse_token(const char *resp, char *out, size_t out_len)
{
    if (!resp || !out || out_len == 0) {
        return false;
    }

    const char *keys[] = { "credentialsValue", "accessToken" };
    for (size_t k = 0; k < sizeof(keys) / sizeof(keys[0]); k++) {
        if (parse_json_string_field(resp, keys[k], out, out_len)) {
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
    if (cfg->device_name[0]) {
        snprintf(dev_name, sizeof(dev_name), "%s", cfg->device_name);
    } else if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK) {
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

    char resp[1024] = {0};
    http_resp_buf_t resp_ctx = {
        .buf = resp,
        .cap = sizeof(resp),
        .len = 0,
        .truncated = false,
    };

    esp_http_client_config_t http_cfg = {
        .url = TB_PROVISION_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 15000,
        .event_handler = http_event_handler,
        .user_data = &resp_ctx,
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
    int total = (int)resp_ctx.len;

    esp_http_client_cleanup(client);

    ESP_LOGI(
        TAG,
        "PROV | http=%d content_len=%d resp=%d bytes%s: %.160s",
        status,
        content_len,
        total,
        resp_ctx.truncated ? " (truncated)" : "",
        resp
    );

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "PROV | http error %s", esp_err_to_name(err));
        return false;
    }
    if (status != 200) {
        ESP_LOGE(TAG, "PROV | http_status=%d", status);
        return false;
    }

    char tb_status[24] = {0};
    char tb_error[160] = {0};
    char token[sizeof(cfg->token)] = {0};
    if (parse_json_string_field(resp, "status", tb_status, sizeof(tb_status)) &&
        strcmp(tb_status, "SUCCESS") != 0) {
        if (parse_json_string_field(resp, "errorMsg", tb_error, sizeof(tb_error))) {
            ESP_LOGE(TAG, "PROV | tb_status=%s msg=%s", tb_status, tb_error);
        } else {
            ESP_LOGE(TAG, "PROV | tb_status=%s", tb_status);
        }
        return false;
    }

    if (total == 0 || !parse_token(resp, token, sizeof(token))) {
        ESP_LOGE(TAG, "PROV | parse token failed");
        return false;
    }

    snprintf(cfg->token, sizeof(cfg->token), "%s", token);
    cfg->backend_synced = 0;

    if (app_config_save(cfg) != ESP_OK) {
        cfg->token[0] = '\0';
        cfg->backend_synced = 0;
        ESP_LOGE(TAG, "PROV | lưu NVS thất bại, hủy token RAM để tránh mất đồng bộ");
        return false;
    }

    ESP_LOGI(TAG, "PROV | thành công (http=200 nvs=saved)");
    return true;
}
