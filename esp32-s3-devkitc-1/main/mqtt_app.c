/*
 * mqtt_app.c — MQTT client kết nối ThingsBoard.
 *
 * Shared attributes chuẩn:
 *   camera_id, capture_interval_ms, jpeg_quality, resolution,
 *   tl_red_ms, tl_yellow_ms, tl_green_ms,
 *   telemetry_interval_ms, target_fw_version, ota_url,
 *   reboot, factory_reset
 *
 * Client attributes chuẩn:
 *   device_model, mac_address, reset_reason, location
 *
 * Telemetry chuẩn:
 *   cpu_temp, free_heap, min_free_heap, wifi_rssi, uptime_s,
 *   device_state, Light_Mode, wifi_disconnect_count
 */
#include "mqtt_app.h"
#include "task_manager.h"
#include "tb_provisioning.h"
#include "app_config.h"
#include "goouuu_camera.h"
#include "led_status.h"
#include "traffic_light.h"
#include "wifi_manager.h"
#include "esp_camera.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "esp_ota_ops.h"
#include "esp_https_ota.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include "mqtt_client.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_event.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "mqtt_app";

/* ThingsBoard RPC response prefix */
#define RPC_RESP_PFX "v1/devices/me/rpc/response/"

/* Thời gian retry provisioning */
#ifndef REPROV_RETRY_MS
#define REPROV_RETRY_MS       3000
#endif
#ifndef BACKEND_SYNC_RETRY_MS
#define BACKEND_SYNC_RETRY_MS 5000
#endif

#ifndef BACKEND_UPLOAD_URL
#  error "BACKEND_UPLOAD_URL chua duoc dinh nghia! Them vao platformio.ini build_flags."
#endif
#ifndef BACKEND_SYNC_DEVICE_PREFIX
#define BACKEND_SYNC_DEVICE_PREFIX "PCB Cam AI S3"
#endif
#ifndef BACKEND_SYNC_DEVICE_MODEL
#define BACKEND_SYNC_DEVICE_MODEL "PCB Cam AI S3"
#endif
#ifndef DEFAULT_DEVICE_LOCATION
#error "DEFAULT_DEVICE_LOCATION chua duoc dinh nghia. Dat trong platformio.ini."
#endif

#define CAPTURE_INTERVAL_MIN_MS   100
#define CAPTURE_INTERVAL_MAX_MS   3600000
#define JPEG_QUALITY_MIN          4
#define JPEG_QUALITY_MAX          63
#define TELEMETRY_INTERVAL_MIN_MS 5000
#define TELEMETRY_INTERVAL_MAX_MS 3600000
#define TL_DURATION_MIN_MS        100
#define TL_DURATION_MAX_MS        3600000

/* State nội bộ */
static esp_mqtt_client_handle_t s_client      = NULL;
static bool                     s_connected   = false;
static bool                     s_initialized = false;
static char                     s_token[128]  = {0};
static char                     s_last_ota_url[256]    = {0};
static bool                     s_ota_active           = false;
static bool                     s_reboot_pending       = false;
static bool                     s_reprovision_pending  = false;
static bool                     s_factory_reset_pending= false;
static app_config_t             s_cfg;
static char                     s_backend_sync_state[16] = "unknown";
static int                      s_backend_sync_attempts = 0;
static const int                BACKEND_SYNC_MAX_ATTEMPTS = 3;

/* Trạng thái disconnect để trigger re-provision */
static TickType_t s_disconnect_tick = 0;
static TickType_t s_last_prov_tick  = 0;
static TickType_t s_last_backend_sync_tick = 0;
static int        s_prov_attempts   = 0;
static bool       s_backend_sync_pending = false;

/* ---------- Helpers ---------- */

static int extract_rpc_id(const char *topic) {
    const char *p = strrchr(topic, '/');
    return (p && *(p+1)) ? atoi(p+1) : -1;
}

static bool parse_bool(const cJSON *item, bool *out) {
    if (!item || !out) return false;
    if (cJSON_IsBool(item))   { *out = cJSON_IsTrue(item); return true; }
    if (cJSON_IsNumber(item)) { *out = (item->valuedouble != 0); return true; }
    if (cJSON_IsString(item)) {
        if (!strcmp(item->valuestring,"true")||!strcmp(item->valuestring,"1"))
            { *out = true; return true; }
        if (!strcmp(item->valuestring,"false")||!strcmp(item->valuestring,"0"))
            { *out = false; return true; }
    }
    return false;
}

static bool parse_int(const cJSON *item, int *out) {
    if (!item || !out) return false;
    if (cJSON_IsNumber(item)) { *out = item->valueint; return true; }
    if (cJSON_IsString(item)) {
        char *e = NULL;
        long v = strtol(item->valuestring, &e, 10);
        if (e && *e == '\0') { *out = (int)v; return true; }
    }
    return false;
}

static bool parse_resolution_framesize(const cJSON *item, int *out)
{
    framesize_t framesize = FRAMESIZE_INVALID;

    if (parse_int(item, out)) {
        return true;
    }
    if (!item || !out || !cJSON_IsString(item) || !item->valuestring || !item->valuestring[0]) {
        return false;
    }
    if (!goouuu_camera_parse_framesize(item->valuestring, &framesize)) {
        return false;
    }
    *out = (int)framesize;
    return true;
}

static bool parse_non_empty_string(const cJSON *item, const char **out)
{
    if (!item || !out || !cJSON_IsString(item) || !item->valuestring || !item->valuestring[0]) {
        return false;
    }
    *out = item->valuestring;
    return true;
}

static const char *get_device_state_label(void)
{
    if (s_ota_active) {
        return "ota";
    }
    if (!g_camera_ok) {
        return "error";
    }
    if (!s_connected) {
        return "wifi_connecting";
    }
    return "running";
}

static void pub_attr_bool(const char *key, bool val) {
    if (!s_client || !s_connected) return;
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"%s\":%s}", key, val ? "true" : "false");
    esp_mqtt_client_publish(s_client, TB_TOPIC_ATTRIBUTES, buf, 0, 1, 0);
}

static void pub_fw_state(const char *state, const char *err) {
    if (!s_client || !s_connected) return;
    char buf[160];
    if (err && err[0])
        snprintf(buf, sizeof(buf), "{\"fw_state\":\"%s\",\"fw_error\":\"%s\"}", state, err);
    else
        snprintf(buf, sizeof(buf), "{\"fw_state\":\"%s\"}", state);
    esp_mqtt_client_publish(s_client, TB_TOPIC_ATTRIBUTES, buf, 0, 1, 0);
}

static void build_stream_url_from_ip(char *out, size_t out_len, const char *ip_address)
{
    if (!out || out_len == 0) {
        return;
    }
    if (!ip_address || !ip_address[0]) {
        out[0] = '\0';
        return;
    }
    snprintf(out, out_len, "http://%s:81/stream", ip_address);
}

static void build_tb_device_name(char *out, size_t out_len, const uint8_t mac[6])
{
    if (!out || out_len == 0) {
        return;
    }
    snprintf(
        out,
        out_len,
        "cam-%02X%02X%02X%02X%02X%02X",
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
    );
}

static void build_device_name(char *out, size_t out_len)
{
    if (!out || out_len == 0) {
        return;
    }
    if (s_cfg.device_name[0]) {
        snprintf(out, out_len, "%s", s_cfg.device_name);
    } else {
        snprintf(out, out_len, "%s %03d", BACKEND_SYNC_DEVICE_PREFIX, g_camera_id > 0 ? (int)g_camera_id : 1);
    }
}

static const char *get_resolution_label(void)
{
    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) {
        const char *label = goouuu_camera_framesize_to_string((framesize_t)sensor->status.framesize);
        if (label && label[0]) {
            return label;
        }
    }
    return "VGA";
}

static bool is_resolution_change_needed(int framesize)
{
    sensor_t *sensor = esp_camera_sensor_get();
    return !sensor || sensor->status.framesize != framesize;
}

static bool is_quality_change_needed(int quality)
{
    sensor_t *sensor = esp_camera_sensor_get();
    return !sensor || sensor->status.quality != quality;
}

static const char* get_reset_reason_str(void)
{
    esp_reset_reason_t reason = esp_reset_reason();
    switch (reason) {
        case ESP_RST_POWERON:  return "POWER_ON";
        case ESP_RST_EXT:      return "EXT_RESET";
        case ESP_RST_SW:       return "SW_RESET";
        case ESP_RST_PANIC:    return "PANIC";
        case ESP_RST_INT_WDT:  return "INT_WDT";
        case ESP_RST_TASK_WDT: return "TASK_WDT";
        case ESP_RST_WDT:      return "WDT_RESET";
        case ESP_RST_DEEPSLEEP:return "DEEP_SLEEP";
        case ESP_RST_BROWNOUT: return "BROWNOUT";
        case ESP_RST_SDIO:     return "SDIO";
        default:               return "UNKNOWN";
    }
}

static void publish_device_runtime_snapshot(const char *status, const char *backend_sync)
{
    if (!s_client || !s_connected) {
        return;
    }

    if (backend_sync && backend_sync[0]) {
        snprintf(s_backend_sync_state, sizeof(s_backend_sync_state), "%s", backend_sync);
    }

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    const esp_app_desc_t *app = esp_app_get_description();
    const char *project_name = (app && app->project_name[0]) ? app->project_name : BACKEND_SYNC_DEVICE_PREFIX;
    const char *resolution = get_resolution_label();

    char ip_address[20] = {0};
    char stream_url[64] = {0};
    char tb_device_name[48] = {0};
    char device_name[64] = {0};
    bool has_ip = wifi_get_ip_string(ip_address, sizeof(ip_address));
    build_stream_url_from_ip(stream_url, sizeof(stream_url), has_ip ? ip_address : "");
    build_tb_device_name(tb_device_name, sizeof(tb_device_name), mac);
    build_device_name(device_name, sizeof(device_name));

    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    cJSON_AddStringToObject(root, "device_model", BACKEND_SYNC_DEVICE_MODEL);
    cJSON_AddStringToObject(root, "device_name", device_name);
    cJSON_AddStringToObject(root, "project_name", project_name);
    cJSON_AddStringToObject(root, "tb_device_name", tb_device_name);
    cJSON_AddStringToObject(root, "fw_version", app ? app->version : "unknown");
    cJSON_AddNumberToObject(root, "camera_id", g_camera_id);
    
    char mac_str[18];
    snprintf(mac_str, sizeof(mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    cJSON_AddStringToObject(root, "mac_address", mac_str);
    
    cJSON_AddStringToObject(root, "location", s_cfg.location);
    cJSON_AddStringToObject(root, "reset_reason", get_reset_reason_str());
    cJSON_AddStringToObject(root, "idf_ver", app ? app->idf_ver : "unknown");
    cJSON_AddStringToObject(root, "wifi_ssid", s_cfg.ssid);
    cJSON_AddStringToObject(root, "resolution", resolution);
    cJSON_AddStringToObject(root, "ip_address", has_ip ? ip_address : "");
    cJSON_AddStringToObject(root, "stream_url", has_ip ? stream_url : "");
    cJSON_AddStringToObject(root, "stream_scheme", "http");
    cJSON_AddStringToObject(root, "stream_host", has_ip ? ip_address : "");
    cJSON_AddNumberToObject(root, "stream_port", 81);
    cJSON_AddStringToObject(root, "stream_path", "/stream");
    cJSON_AddStringToObject(root, "stream_snapshot_path", "/snapshot");
    cJSON_AddStringToObject(root, "backend_url", BACKEND_UPLOAD_URL);
    cJSON_AddStringToObject(root, "device_status", status ? status : "unknown");
    cJSON_AddStringToObject(root, "backend_sync", backend_sync ? backend_sync : "unknown");

    char *attrs = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (attrs) {
        esp_mqtt_client_publish(s_client, TB_TOPIC_ATTRIBUTES, attrs, 0, 1, 0);
        free(attrs);
    }

    char telem[384];
    snprintf(
        telem,
        sizeof(telem),
        "{\"status\":\"%s\",\"ip_address\":\"%s\",\"stream_url\":\"%s\","
        "\"device_name\":\"%s\",\"tb_device_name\":\"%s\",\"backend_sync\":\"%s\","
        "\"device_state\":\"%s\",\"wifi_rssi\":%d,\"wifi_disconnect_count\":%lu}",
        status ? status : "unknown",
        has_ip ? ip_address : "",
        has_ip ? stream_url : "",
        device_name,
        tb_device_name,
        backend_sync ? backend_sync : "unknown",
        get_device_state_label(),
        (int)get_wifi_rssi(),
        (unsigned long)g_wifi_disconnect_count
    );
    esp_mqtt_client_publish(s_client, TB_TOPIC_TELEMETRY, telem, 0, 1, 0);
}

static void build_backend_url(char *out, size_t out_len, const char *path)
{
    size_t base_len = strlen(BACKEND_UPLOAD_URL);
    bool base_has_slash = (base_len > 0 && BACKEND_UPLOAD_URL[base_len - 1] == '/');
    bool path_has_slash = (path && path[0] == '/');

    if (!out || out_len == 0 || !path) {
        return;
    }

    if (base_has_slash && path_has_slash) {
        snprintf(out, out_len, "%s%s", BACKEND_UPLOAD_URL, path + 1);
    } else if (!base_has_slash && !path_has_slash) {
        snprintf(out, out_len, "%s/%s", BACKEND_UPLOAD_URL, path);
    } else {
        snprintf(out, out_len, "%s%s", BACKEND_UPLOAD_URL, path);
    }
}

static bool sync_backend_provisioning(void)
{
    if (!s_token[0]) {
        ESP_LOGW(TAG, "Bỏ qua đồng bộ backend vì chưa có access token");
        return false;
    }
    if (g_camera_id <= 0) {
        ESP_LOGW(TAG, "Bỏ qua đồng bộ backend vì camera_id không hợp lệ");
        return false;
    }

    char ip_address[20] = {0};
    if (!wifi_get_ip_string(ip_address, sizeof(ip_address))) {
        ESP_LOGW(TAG, "Chưa lấy được IP WiFi để đồng bộ backend");
        return false;
    }

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    char mac_address[18];
    char tb_device_name[48];
    char device_name[64];
    char stream_url[64];
    const esp_app_desc_t *app = esp_app_get_description();
    const char *project_name = (app && app->project_name[0]) ? app->project_name : BACKEND_SYNC_DEVICE_PREFIX;
    const char *resolution = get_resolution_label();
    snprintf(
        mac_address,
        sizeof(mac_address),
        "%02X:%02X:%02X:%02X:%02X:%02X",
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
    );
    build_tb_device_name(tb_device_name, sizeof(tb_device_name), mac);
    build_device_name(device_name, sizeof(device_name));
    build_stream_url_from_ip(stream_url, sizeof(stream_url), ip_address);

    char url[280];
    build_backend_url(url, sizeof(url), "/api/cameras/provision");

    cJSON *root = cJSON_CreateObject();
    if (!root) {
        ESP_LOGE(TAG, "Không đủ bộ nhớ tạo JSON payload");
        return false;
    }

    cJSON_AddNumberToObject(root, "camera_id", g_camera_id);
    cJSON_AddStringToObject(root, "camera_name", device_name);
    cJSON_AddStringToObject(root, "tb_device_id", tb_device_name);
    cJSON_AddStringToObject(root, "tb_device_name", tb_device_name);
    cJSON_AddStringToObject(root, "device_name", device_name);
    cJSON_AddStringToObject(root, "project_name", project_name);
    cJSON_AddStringToObject(root, "device_model", BACKEND_SYNC_DEVICE_MODEL);
    cJSON_AddStringToObject(root, "location", s_cfg.location);
    cJSON_AddStringToObject(root, "reset_reason", get_reset_reason_str());
    cJSON_AddStringToObject(root, "wifi_ssid", s_cfg.ssid);
    cJSON_AddStringToObject(root, "resolution", resolution);
    cJSON_AddStringToObject(root, "access_token", s_token);
    cJSON_AddStringToObject(root, "mac_address", mac_address);
    cJSON_AddStringToObject(root, "fw_version", app ? app->version : "unknown");
    cJSON_AddStringToObject(root, "idf_version", app ? app->idf_ver : "unknown");
    cJSON_AddStringToObject(root, "stream_scheme", "http");
    cJSON_AddStringToObject(root, "stream_host", ip_address);
    cJSON_AddNumberToObject(root, "stream_port", 81);
    cJSON_AddStringToObject(root, "stream_path", "/stream");
    cJSON_AddStringToObject(root, "stream_snapshot_path", "/snapshot");
    cJSON_AddStringToObject(root, "stream_url", stream_url);
    cJSON_AddStringToObject(root, "ip_address", ip_address);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (!body) {
        ESP_LOGE(TAG, "Lỗi in JSON payload");
        return false;
    }

    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 5000,
    };
    if (strncmp(url, "https", 5) == 0) {
        cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) {
        ESP_LOGE(TAG, "Không tạo được HTTP client để đồng bộ backend");
        free(body);
        return false;
    }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, strlen(body));

    esp_err_t err = esp_http_client_perform(client);
    bool success = false;
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        if (status >= 200 && status < 300) {
            ESP_LOGI(TAG, "Đã đồng bộ provisioning lên backend thành công (status=%d)", status);
            success = true;
        } else {
            ESP_LOGW(TAG, "Đồng bộ provisioning lên backend thất bại camera=%d status=%d err=%s", 
                     g_camera_id, status, esp_err_to_name(err));
            
            // Log response body if possible
            int content_len = esp_http_client_get_content_length(client);
            if (content_len > 0 && content_len < 512) {
                char resp_buf[512] = {0};
                int read_len = esp_http_client_read(client, resp_buf, sizeof(resp_buf) - 1);
                if (read_len > 0) {
                    ESP_LOGD(TAG, "Backend Response: %s", resp_buf);
                }
            }
        }
    } else {
        ESP_LOGW(TAG, "Đồng bộ provisioning lên backend gặp lỗi kết nối camera=%d err=%s", 
                 g_camera_id, esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    free(body);
    return success;
}

static void trigger_reprovision_restart(const char *source)
{
    ESP_LOGW(
        TAG,
        "Yêu cầu provision lại từ %s: xóa token cũ, giữ WiFi và provisioning credentials",
        source ? source : "unknown"
    );

    if (app_config_clear_token() != ESP_OK) {
        ESP_LOGE(TAG, "Không xóa được token cũ để provision lại");
        return;
    }

    s_cfg.token[0] = '\0';
    s_token[0] = '\0';
    pub_attr_bool("reprovision", false);
    vTaskDelay(pdMS_TO_TICKS(300));
    esp_restart();
}

/* ---------- OTA task ---------- */

static void ota_task(void *pv)
{
    char *url = (char *)pv;
    if (!url) { s_ota_active = false; vTaskDelete(NULL); return; }

    ESP_LOGI(TAG, "🔄 OTA bắt đầu: %s", url);
    led_status_set_rgb(0, 0, 64); /* Xanh dương — đang OTA */
    pub_fw_state("DOWNLOADING", NULL);

    esp_http_client_config_t hcfg = {
        .url         = url,
        .timeout_ms  = 30000,
    };
    if (strncmp(url, "https", 5) == 0)
        hcfg.crt_bundle_attach = esp_crt_bundle_attach;

    esp_https_ota_config_t ocfg = { .http_config = &hcfg };
    esp_err_t ret = esp_https_ota(&ocfg);

    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ OTA thành công - hệ thống khởi động lại...");
        led_status_set_rgb(0, 64, 0);
        pub_fw_state("UPDATED", NULL);
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    } else {
        ESP_LOGE(TAG, "❌ OTA thất bại: %s", esp_err_to_name(ret));
        led_status_set_rgb(64, 0, 0);
        pub_fw_state("FAILED", esp_err_to_name(ret));
        vTaskDelay(pdMS_TO_TICKS(2000));
        led_status_white();
    }

    free(url);
    s_ota_active = false;
    vTaskDelete(NULL);
}

static void start_ota(const char *url)
{
    if (!url || url[0] == '\0') return;
    if (s_ota_active) { ESP_LOGW(TAG, "OTA đang chạy, bỏ qua"); return; }

    strncpy(s_last_ota_url, url, sizeof(s_last_ota_url) - 1);
    s_ota_active = true;

    char *copy = strdup(url);
    if (!copy || xTaskCreate(ota_task, "ota", 8192, copy, 3, NULL) != pdPASS) {
        free(copy);
        s_ota_active = false;
        ESP_LOGE(TAG, "Không tạo được OTA task");
    }
}

/* ---------- Attributes handler ---------- */

static void handle_attributes(const char *data, int len)
{
    cJSON *root = cJSON_ParseWithLength(data, len);
    if (!root) {
        ESP_LOGW(TAG, "Lỗi phân giải JSON attributes");
        return;
    }

    /* ThingsBoard bọc trong "shared" khi response request */
    cJSON *node = cJSON_GetObjectItem(root, "shared");
    if (!node || !cJSON_IsObject(node)) node = root;

    const cJSON *item;
    const char *ota_url_value = NULL;
    const esp_app_desc_t *app = esp_app_get_description();
    bool bval;
    int ival;

    item = cJSON_GetObjectItem(node, "camera_id");
    if (parse_int(item, &ival) && ival > 0) {
        if (g_camera_id != ival) {
            ESP_LOGI(TAG, "Cập nhật camera_id từ ThingsBoard: %d -> %d", g_camera_id, ival);
            s_backend_sync_pending = true;
        }
        g_camera_id = ival;
        publish_device_runtime_snapshot("online", s_backend_sync_pending ? "pending" : s_backend_sync_state);
    }

    item = cJSON_GetObjectItem(node, "capture_interval_ms");
    if (parse_int(item, &ival)) {
        if (ival < CAPTURE_INTERVAL_MIN_MS || ival > CAPTURE_INTERVAL_MAX_MS) {
            ESP_LOGW(TAG, "Bỏ qua capture_interval_ms không hợp lệ: %d", ival);
        } else if (g_mqtt_cmd_queue) {
            mqtt_cmd_msg_t cmd = {0};
            cmd.cmd = MQTT_CMD_CAPTURE_INTERVAL;
            cmd.payload.interval.interval_ms = ival;
            xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
            ESP_LOGI(TAG, "Cập nhật capture_interval_ms = %d", ival);
        }
    }

    item = cJSON_GetObjectItem(node, "jpeg_quality");
    if (parse_int(item, &ival)) {
        if (ival < JPEG_QUALITY_MIN || ival > JPEG_QUALITY_MAX) {
            ESP_LOGW(TAG, "Bỏ qua jpeg_quality không hợp lệ: %d", ival);
        } else if (g_mqtt_cmd_queue && is_quality_change_needed(ival)) {
            mqtt_cmd_msg_t cmd = {0};
            cmd.cmd = MQTT_CMD_CAMERA_QUALITY;
            cmd.payload.quality.quality = ival;
            xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
            ESP_LOGI(TAG, "🎥 Cập nhật jpeg_quality: %d", ival);
        }
    }

    item = cJSON_GetObjectItem(node, "resolution");
    if (parse_resolution_framesize(item, &ival)) {
        if (g_mqtt_cmd_queue && is_resolution_change_needed(ival)) {
            mqtt_cmd_msg_t cmd = {0};
            cmd.cmd = MQTT_CMD_CAMERA_RESOLUTION;
            cmd.payload.resolution.framesize = ival;
            xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
            ESP_LOGI(TAG, "🎥 Cập nhật resolution: %d", ival);
        }
    }

    item = cJSON_GetObjectItem(node, "reboot");
    if (parse_bool(item, &bval) && bval && !s_reboot_pending) {
        s_reboot_pending = true;
        pub_attr_bool("reboot", false);
        vTaskDelay(pdMS_TO_TICKS(300));
        esp_restart();
    }

    item = cJSON_GetObjectItem(node, "factory_reset");
    if (parse_bool(item, &bval) && bval && !s_factory_reset_pending) {
        s_factory_reset_pending = true;
        pub_attr_bool("factory_reset", false);
        ESP_LOGW(TAG, "Factory reset được yêu cầu");
        vTaskDelay(pdMS_TO_TICKS(300));
        app_config_clear();
        esp_restart();
    }

    item = cJSON_GetObjectItem(node, "ota_url");
    parse_non_empty_string(item, &ota_url_value);

    const cJSON *target_fw = cJSON_GetObjectItem(node, "target_fw_version");
    if (target_fw && cJSON_IsString(target_fw) && target_fw->valuestring[0]) {
        if (app && strcmp(app->version, target_fw->valuestring) == 0) {
            ESP_LOGI(TAG, "Firmware đã ở đúng target_fw_version=%s", target_fw->valuestring);
        } else if (ota_url_value && !s_ota_active &&
                   strcmp(s_last_ota_url, ota_url_value) != 0) {
            ESP_LOGI(TAG, "Kích hoạt OTA target_fw_version=%s qua ota_url", target_fw->valuestring);
            start_ota(ota_url_value);
        } else if (!ota_url_value) {
            ESP_LOGW(TAG, "Nhận target_fw_version=%s nhưng chưa có ota_url", target_fw->valuestring);
        }
    } else if (ota_url_value && !s_ota_active &&
               strcmp(s_last_ota_url, ota_url_value) != 0) {
        ESP_LOGI(TAG, "Kích hoạt OTA qua ota_url");
        start_ota(ota_url_value);
    }

    uint32_t tl_r = 0;
    uint32_t tl_y = 0;
    uint32_t tl_g = 0;

    item = cJSON_GetObjectItem(node, "tl_red_ms");
    if (parse_int(item, &ival)) {
        if (ival >= TL_DURATION_MIN_MS && ival <= TL_DURATION_MAX_MS) {
            tl_r = (uint32_t)ival;
        } else {
            ESP_LOGW(TAG, "Bỏ qua tl_red_ms không hợp lệ: %d", ival);
        }
    }

    item = cJSON_GetObjectItem(node, "tl_yellow_ms");
    if (parse_int(item, &ival)) {
        if (ival >= TL_DURATION_MIN_MS && ival <= TL_DURATION_MAX_MS) {
            tl_y = (uint32_t)ival;
        } else {
            ESP_LOGW(TAG, "Bỏ qua tl_yellow_ms không hợp lệ: %d", ival);
        }
    }

    item = cJSON_GetObjectItem(node, "tl_green_ms");
    if (parse_int(item, &ival)) {
        if (ival >= TL_DURATION_MIN_MS && ival <= TL_DURATION_MAX_MS) {
            tl_g = (uint32_t)ival;
        } else {
            ESP_LOGW(TAG, "Bỏ qua tl_green_ms không hợp lệ: %d", ival);
        }
    }

    if (tl_r || tl_y || tl_g)
        traffic_light_set_timings(tl_r, tl_y, tl_g);

    item = cJSON_GetObjectItem(node, "telemetry_interval_ms");
    if (parse_int(item, &ival)) {
        if (ival >= TELEMETRY_INTERVAL_MIN_MS && ival <= TELEMETRY_INTERVAL_MAX_MS) {
            g_telemetry_interval_ms = (uint32_t)ival;
            ESP_LOGI(TAG, "Cập nhật telemetry_interval_ms = %d ms", ival);
        } else {
            ESP_LOGW(TAG, "Bỏ qua telemetry_interval_ms không hợp lệ: %d", ival);
        }
    }

    item = cJSON_GetObjectItem(node, "inactivity_alarm_time");
    if (parse_int(item, &ival) && ival > 0) {
        ESP_LOGI(TAG, "inactivity_alarm_time = %d (chưa có logic xử lý)", ival);
    }

    cJSON_Delete(root);
}

/* ---------- RPC handler ---------- */

static void handle_rpc(const char *topic, const char *data, int len)
{
    int req_id = extract_rpc_id(topic);
    if (req_id < 0) return;

    cJSON *json   = cJSON_ParseWithLength(data, len);
    if (!json) { mqtt_app_send_rpc_response(req_id, false, "JSON loi"); return; }

    cJSON *method = cJSON_GetObjectItem(json, "method");
    cJSON *params = cJSON_GetObjectItem(json, "params");
    if (!method || !cJSON_IsString(method)) {
        mqtt_app_send_rpc_response(req_id, false, "Thieu method");
        cJSON_Delete(json); return;
    }

    const char *m = method->valuestring;
    ESP_LOGI(TAG, "RPC [%d] method=%s", req_id, m);

    mqtt_cmd_msg_t cmd = {0};
    cmd.request_id = req_id;
    bool enqueue = false;

    if (!strcmp(m, "setResolution")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "framesize") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAMERA_RESOLUTION;
            cmd.payload.resolution.framesize = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "Thieu framesize"); }
    }
    else if (!strcmp(m, "setQuality")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "quality") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAMERA_QUALITY;
            cmd.payload.quality.quality = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "Thieu quality"); }
    }
    else if (!strcmp(m, "setInterval")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "interval_ms") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAPTURE_INTERVAL;
            cmd.payload.interval.interval_ms = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "Thieu interval_ms"); }
    }
    else if (!strcmp(m, "reboot")) {
        mqtt_app_send_rpc_response(req_id, true, "Dang khoi dong lai...");
        vTaskDelay(pdMS_TO_TICKS(500));
        esp_restart();
    }
    else if (!strcmp(m, "reprovision")) {
        mqtt_app_send_rpc_response(req_id, true, "Dang xoa token cu de provision lai...");
        s_reprovision_pending = true;
        vTaskDelay(pdMS_TO_TICKS(300));
        trigger_reprovision_restart("rpc");
    }
    else if (!strcmp(m, "startOTA")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "url") : NULL;
        if (p && cJSON_IsString(p)) {
            mqtt_app_send_rpc_response(req_id, true, "OTA bat dau");
            start_ota(p->valuestring);
        } else { mqtt_app_send_rpc_response(req_id, false, "Thieu url"); }
    }
    else if (!strcmp(m, "getStatus")) {
        char ip_address[20] = {0};
        char stream_url[64] = {0};
        bool has_ip = wifi_get_ip_string(ip_address, sizeof(ip_address));
        build_stream_url_from_ip(stream_url, sizeof(stream_url), has_ip ? ip_address : "");
        const esp_app_desc_t *app = esp_app_get_description();
        uint32_t uptime_s = (uint32_t)(esp_timer_get_time() / 1000000ULL);

        char st[768];
        snprintf(st, sizeof(st),
                 "{\"status\":\"online\",\"camera_id\":%d,"
                 "\"device_state\":\"%s\",\"fw_version\":\"%s\","
                 "\"free_heap\":%lu,\"capture_interval_ms\":%lu,"
                 "\"telemetry_interval_ms\":%lu,\"uptime_s\":%lu,"
                 "\"camera_ok\":%s,\"mqtt_connected\":%s,"
                 "\"wifi_rssi\":%d,\"wifi_disconnect_count\":%lu,"
                 "\"ip_address\":\"%s\",\"stream_url\":\"%s\","
                 "\"backend_url\":\"%s\",\"backend_sync\":\"%s\"}",
                 g_camera_id,
                 get_device_state_label(),
                 app ? app->version : "unknown",
                 (unsigned long)esp_get_free_heap_size(),
                 (unsigned long)g_capture_interval_ms,
                 (unsigned long)g_telemetry_interval_ms,
                 (unsigned long)uptime_s,
                 g_camera_ok ? "true" : "false",
                 s_connected ? "true" : "false",
                 (int)get_wifi_rssi(),
                 (unsigned long)g_wifi_disconnect_count,
                 has_ip ? ip_address : "",
                 has_ip ? stream_url : "",
                 BACKEND_UPLOAD_URL,
                 s_backend_sync_state);
        mqtt_app_send_rpc_response(req_id, true, st);
    }
    else if (!strcmp(m, "factoryReset")) {
        mqtt_app_send_rpc_response(req_id, true, "Factory reset...");
        vTaskDelay(pdMS_TO_TICKS(300));
        app_config_clear();
        esp_restart();
    }
    /* ---- Đèn giao thông RPC ---- */
    else if (!strcmp(m, "setNormalMode") ||
             !strcmp(m, "setEmergencyRed") ||
             !strcmp(m, "setEmergencyGreen")) {
        if (traffic_light_handle_rpc(m)) {
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else {
            mqtt_app_send_rpc_response(req_id, false, "Loi traffic_light");
        }
    }
    else if (!strcmp(m, "getTrafficStatus")) {
        tl_status_t st = traffic_light_get_status();
        const char *s  = (st.state == TL_STATE_RED)    ? "red" :
                         (st.state == TL_STATE_YELLOW)  ? "yellow" : "green";
        const char *md = (st.mode  == TL_MODE_NORMAL)          ? "normal" :
                         (st.mode  == TL_MODE_EMERGENCY_RED)    ? "emergency_red" :
                                                                   "emergency_green";
        char resp[320];
        snprintf(resp, sizeof(resp),
                 "{\"traffic_light_state\":\"%s\",\"phase\":\"%s\","
                 "\"operation_mode\":\"%s\",\"state_ms\":%lu,"
                 "\"phase_duration_ms\":%lu,\"phase_start_ms\":%lu,"
                 "\"remain_sec\":%lu}",
                 s, s, md,
                 (unsigned long)st.state_ms,
                 (unsigned long)st.phase_duration_ms,
                 (unsigned long)st.phase_start_ms,
                 (unsigned long)st.remain_sec);
        mqtt_app_send_rpc_response(req_id, true, resp);
    }
    else {
        ESP_LOGW(TAG, "RPC không biết: %s", m);
        mqtt_app_send_rpc_response(req_id, false, "Method khong ho tro");
    }

    if (enqueue && g_mqtt_cmd_queue) {
        xQueueSend(g_mqtt_cmd_queue, &cmd, pdMS_TO_TICKS(100));
    }
    cJSON_Delete(json);
}


/* ---------- Bckend Sync Background Task ---------- */
static void backend_sync_task(void *pvParameter)
{
    if (s_cfg.backend_synced == 1 && s_connected) {
        ESP_LOGI(TAG, "⚡ Đã đồng bộ backend từ trước (NVS), bỏ qua sync");
        publish_device_runtime_snapshot("online", "synced");
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Task Backend Sync khởi động (để không block MQTT)");
    int attempts = 0;
    while (attempts < BACKEND_SYNC_MAX_ATTEMPTS && g_system_running) {
        if (!s_connected) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }
        
        if (sync_backend_provisioning()) {
            ESP_LOGI(TAG, "✅ Đồng bộ backend thành công (lần %d)", attempts + 1);
            publish_device_runtime_snapshot("online", "synced");
            s_cfg.backend_synced = 1;
            app_config_save(&s_cfg);
            break;
        }
        attempts++;
        if (attempts >= BACKEND_SYNC_MAX_ATTEMPTS) {
            ESP_LOGW(TAG, "⚠️ Bỏ qua đồng bộ backend sau %d lần thử", attempts);
            publish_device_runtime_snapshot("online", "failed");
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(BACKEND_SYNC_RETRY_MS));
    }
    
    ESP_LOGI(TAG, "Task Backend Sync kết thúc");
    vTaskDelete(NULL);
}

/* ---------- MQTT event handler ---------- */

static void mqtt_evt_handler(void *arg, esp_event_base_t base,
                             int32_t id, void *edata)
{
    esp_mqtt_event_handle_t ev = (esp_mqtt_event_handle_t)edata;

    switch (id) {
    case MQTT_EVENT_CONNECTED: {
        s_connected = true;
        s_disconnect_tick = 0;
        s_prov_attempts   = 0;
        ESP_LOGI(TAG, "🚀 MQTT đã kết nối với ThingsBoard");

        /* Subscribe */
        esp_mqtt_client_subscribe(ev->client, TB_TOPIC_RPC_REQUEST,  1);
        esp_mqtt_client_subscribe(ev->client, TB_TOPIC_ATTRIBUTES,    1);

        /* Yêu cầu shared attributes */
        esp_mqtt_client_publish(ev->client, TB_TOPIC_ATTRIBUTES_REQ,
            "{\"sharedKeys\":\"camera_id,capture_interval_ms,jpeg_quality,resolution,"
            "reboot,factory_reset,ota_url,target_fw_version,telemetry_interval_ms,"
            "tl_red_ms,tl_yellow_ms,tl_green_ms\"}",
            0, 1, 0);

        publish_device_runtime_snapshot("online", "pending");
        
        /* Chạy backend sync trên background task để không block MQTT/Queue */
        xTaskCreate(backend_sync_task, "backend_sync", 8192, NULL, 5, NULL);
        break;
    }

    case MQTT_EVENT_DISCONNECTED:
        s_connected = false;
        s_backend_sync_pending = true;
        if (s_disconnect_tick == 0) s_disconnect_tick = xTaskGetTickCount();
        ESP_LOGW(TAG, "⚠️ Mất kết nối MQTT");
        break;

    case MQTT_EVENT_DATA:
        if (ev->topic_len > 0 && ev->data_len > 0) {
            char *topic = strndup(ev->topic, ev->topic_len);
            if (topic) {
                if (strstr(topic, "rpc/request/"))
                    handle_rpc(topic, ev->data, ev->data_len);
                else if (strstr(topic, "attributes"))
                    handle_attributes(ev->data, ev->data_len);
                free(topic);
            }
        }
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "Lỗi kết nối MQTT");
        break;

    default: break;
    }
}

/* ---------- Khởi tạo client ---------- */

static bool mqtt_client_create(const char *token)
{
    if (s_client) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
        s_initialized = false;
        s_connected   = false;
    }
    if (!token || !token[0]) return false;

    strncpy(s_token, token, sizeof(s_token) - 1);

    esp_mqtt_client_config_t cfg = {
        .broker.address.uri  = MQTT_BROKER_URI,
        .credentials.username= s_token,
        .session.keepalive   = 30,
    };

    s_client = esp_mqtt_client_init(&cfg);
    if (!s_client) { ESP_LOGE(TAG, "MQTT client init thất bại"); return false; }

    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID,
                                   mqtt_evt_handler, NULL);
    if (esp_mqtt_client_start(s_client) != ESP_OK) {
        ESP_LOGE(TAG, "MQTT start thất bại");
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
        return false;
    }
    s_initialized = true;
    return true;
}

/* ---------- Public API ---------- */

void mqtt_app_init(const char *token)
{
    if (s_initialized) return;
    if (!mqtt_client_create(token))
        ESP_LOGW(TAG, "MQTT không khởi tạo được (không có token)");
    else
        ESP_LOGI(TAG, "MQTT đã khởi tạo -> %s", MQTT_BROKER_URI);
}

void mqtt_app_start(const char *token) { mqtt_app_init(token); }

bool mqtt_app_is_connected(void) { return s_connected; }

bool mqtt_app_is_ota_active(void) { return s_ota_active; }

void mqtt_app_send_rpc_response(int req_id, bool success, const char *msg)
{
    if (!s_client || !s_connected || req_id < 0) return;
    char topic[80];
    snprintf(topic, sizeof(topic), "%s%d", RPC_RESP_PFX, req_id);
    
    char *payload = NULL;
    if (msg && msg[0] == '{') {
        payload = strdup(msg);
    } else {
        cJSON *root = cJSON_CreateObject();
        if (!root) return;
        cJSON_AddBoolToObject(root, "success", success);
        cJSON_AddStringToObject(root, "msg", msg ? msg : "");
        payload = cJSON_PrintUnformatted(root);
        cJSON_Delete(root);
    }

    if (payload) {
        esp_mqtt_client_publish(s_client, topic, payload, 0, 1, 0);
        free(payload);
    }
}

void mqtt_app_publish_telemetry(const telemetry_msg_t *t)
{
    if (!s_client || !s_connected || !t) return;
    char *buf = NULL;
    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    switch (t->type) {
    case TELEMETRY_HEALTH: {
        const health_telemetry_t *h = &t->data.health;
        const char *lm_str = (h->light_state == TL_STATE_RED) ? "RED" :
                             (h->light_state == TL_STATE_YELLOW) ? "YELLOW" : "GREEN";
        
        cJSON_AddNumberToObject(root, "free_heap", h->free_heap);
        cJSON_AddNumberToObject(root, "min_free_heap", h->min_free_heap);
        cJSON_AddNumberToObject(root, "wifi_rssi", h->wifi_rssi);
        cJSON_AddNumberToObject(root, "uptime_s", h->uptime_sec);
        cJSON_AddBoolToObject(root, "camera_ok", h->camera_ok);
        cJSON_AddBoolToObject(root, "mqtt_connected", h->mqtt_connected);
        cJSON_AddNumberToObject(root, "wifi_disconnect_count", h->wifi_disconnect_count);
        cJSON_AddStringToObject(root, "device_state", h->device_state[0] ? h->device_state : "online");
        cJSON_AddNumberToObject(root, "last_seen_ts", h->last_seen_ts);
        cJSON_AddStringToObject(root, "Light_Mode", lm_str);
        cJSON_AddNumberToObject(root, "cpu_temp", h->cpu_temp);
        break;
    }
    case TELEMETRY_STATUS:
        cJSON_AddStringToObject(root, "status", t->data.status.status);
        break;
    case TELEMETRY_EVENT:
        cJSON_AddStringToObject(root, t->data.event.key[0] ? t->data.event.key : "event", t->data.event.value);
        break;
    case TELEMETRY_TRAFFIC_LIGHT: {
        static const char *tl_states[] = { "red", "yellow", "green" };
        static const char *tl_modes[]  = { "normal", "emergency_red", "emergency_green" };
        const tl_telemetry_t *tl = &t->data.traffic;
        uint8_t si = tl->state < 3 ? tl->state : 0;
        uint8_t mi = tl->mode  < 3 ? tl->mode  : 0;

        cJSON_AddStringToObject(root, "traffic_light_state", tl_states[si]);
        cJSON_AddStringToObject(root, "phase", tl_states[si]);
        cJSON_AddStringToObject(root, "operation_mode", tl_modes[mi]);
        cJSON_AddNumberToObject(root, "tl_state_ms", tl->state_ms);
        cJSON_AddNumberToObject(root, "phase_duration_ms", tl->phase_duration_ms);
        cJSON_AddNumberToObject(root, "phase_start_ms", tl->phase_start_ms);
        cJSON_AddNumberToObject(root, "remain_sec", tl->remain_sec);
        cJSON_AddNumberToObject(root, "red_ms", tl->red_ms);
        cJSON_AddNumberToObject(root, "yellow_ms", tl->yellow_ms);
        cJSON_AddNumberToObject(root, "green_ms", tl->green_ms);
        cJSON_AddBoolToObject(root, "red_on", tl->red_on);
        cJSON_AddBoolToObject(root, "yellow_on", tl->yellow_on);
        cJSON_AddBoolToObject(root, "green_on", tl->green_on);
        break;
    }
    default:
        cJSON_Delete(root);
        return;
    }

    buf = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (buf) {
        esp_mqtt_client_publish(s_client, TB_TOPIC_TELEMETRY, buf, 0, 1, 0);
        free(buf);
    }
}

/* ---------- MQTT task ---------- */

void mqtt_task(void *pvParameter)
{
    const char *init_token = (const char *)pvParameter;
    telemetry_msg_t telem;

    ESP_LOGI(TAG, "Task MQTT khởi động");

    /* Đọc config để re-provision nếu cần */
    app_config_state_t state;
    if (app_config_load(&s_cfg, &state) != ESP_OK)
        app_config_set_defaults(&s_cfg);

    /* Kết nối MQTT với token có sẵn hoặc thử provision */
    if (init_token && init_token[0]) {
        mqtt_app_init(init_token);
    } else {
        ESP_LOGW(TAG, "Không có token - sẽ thử provisioning");
    }

    while (g_system_running) {
        /* Re-provision nếu mất kết nối */
        if (!s_initialized || (!s_connected && s_disconnect_tick > 0)) {
            TickType_t now = xTaskGetTickCount();
            if (s_last_prov_tick == 0 ||
                (now - s_last_prov_tick) >= pdMS_TO_TICKS(REPROV_RETRY_MS)) {
                s_last_prov_tick = now;
                if (tb_has_prov_credentials(&s_cfg)) {
                    s_prov_attempts++;
                    ESP_LOGI(TAG, "Thử provisioning lần %d...", s_prov_attempts);
                    led_status_set_rgb(0, 32, 32); /* Cyan */
                    if (tb_provision_device(&s_cfg)) {
                        led_status_white();
                        mqtt_client_create(s_cfg.token);
                        s_disconnect_tick = 0;
                    } else {
                        led_status_set_rgb(64, 32, 0); /* Cam */
                        vTaskDelay(pdMS_TO_TICKS(500));
                        led_status_white();
                    }
                }
            }
        }

        /* (Backend sync đã chuyển sang task ngầm `backend_sync_task`) */

        while (xQueueReceive(g_telemetry_queue, &telem,
                             pdMS_TO_TICKS(100)) == pdTRUE) {
            if (s_connected)
                mqtt_app_publish_telemetry(&telem);
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }

    if (s_client) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
    }
    ESP_LOGI(TAG, "🏁 Task MQTT kết thúc");
    vTaskDelete(NULL);
}
