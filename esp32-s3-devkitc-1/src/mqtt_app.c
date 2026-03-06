/*
 * mqtt_app.c — MQTT client kết nối ThingsBoard
 *
 * Shared Attributes đọc từ ThingsBoard:
 *   fw_version, active, frames_per_upload, jpeg_quality, reboot,
 *   resolution, factory_reset, ota_url, fw_title, fw_version,
 *   tl_red_ms, tl_yellow_ms, tl_green_ms, tl_mode (traffic light)
 *
 * Telemetry gửi lên (qua health_task):
 *   upload_ok, last_http_code, latency_ms, Wifi_Status, free_heap...
 *
 * Client Attributes (điều khiển → ThingsBoard):
 *   Model, fw_version, camera_id, mac
 *
 * RPC methods: setResolution, setQuality, setInterval, reboot, startOTA,
 *              getStatus, factoryReset,
 *              setNormalMode, setEmergencyRed, setEmergencyGreen, getTrafficStatus
 */
#include "mqtt_app.h"
#include "task_manager.h"
#include "tb_provisioning.h"
#include "app_config.h"
#include "led_status.h"
#include "traffic_light.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "esp_ota_ops.h"
#include "esp_https_ota.h"
#include "esp_crt_bundle.h"
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
#define REPROV_RETRY_MS  3000

/* State nội bộ */
static esp_mqtt_client_handle_t s_client      = NULL;
static bool                     s_connected   = false;
static bool                     s_initialized = false;
static char                     s_token[128]  = {0};
static char                     s_last_ota_url[256]    = {0};
static char                     s_last_fw_title[64]    = {0};
static char                     s_last_fw_version[32]  = {0};
static bool                     s_ota_active           = false;
static bool                     s_reboot_pending       = false;
static bool                     s_factory_reset_pending= false;
static app_config_t             s_cfg;

/* Trạng thái disconnect để trigger re-provision */
static TickType_t s_disconnect_tick = 0;
static TickType_t s_last_prov_tick  = 0;
static int        s_prov_attempts   = 0;

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

/* ---------- OTA task ---------- */

static void ota_task(void *pv)
{
    char *url = (char *)pv;
    if (!url) { s_ota_active = false; vTaskDelete(NULL); return; }

    ESP_LOGI(TAG, "OTA bắt đầu: %s", url);
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
        ESP_LOGI(TAG, "OTA thành công — đang khởi động lại...");
        led_status_set_rgb(0, 64, 0);
        pub_fw_state("UPDATED", NULL);
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    } else {
        ESP_LOGE(TAG, "OTA thất bại: %s", esp_err_to_name(ret));
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
    if (!root) { ESP_LOGW(TAG, "Parse attributes JSON thất bại"); return; }

    /* ThingsBoard bọc trong "shared" khi response request */
    cJSON *node = cJSON_GetObjectItem(root, "shared");
    if (!node || !cJSON_IsObject(node)) node = root;

    /* --- save_img / cam_id / frames_per_upload --- */
    const cJSON *item;
    bool bval; int ival;

    item = cJSON_GetObjectItem(node, "save_img");
    if (parse_bool(item, &bval)) g_save_img = bval;

    item = cJSON_GetObjectItem(node, "camera_id");
    if (!item) item = cJSON_GetObjectItem(node, "cam_id");
    if (parse_int(item, &ival) && ival > 0) g_camera_id = ival;

    item = cJSON_GetObjectItem(node, "frames_per_upload");
    if (parse_int(item, &ival) && ival > 0 &&
        ival <= APP_CONFIG_MAX_FRAMES_PER_UPLOAD) {
        if (g_frames_per_upload != (uint16_t)ival) {
            g_frames_per_upload   = (uint16_t)ival;
            s_cfg.frames_per_upload = (uint16_t)ival;
            g_frames_upload_epoch++;
            app_config_save(&s_cfg);
            ESP_LOGI(TAG, "frames_per_upload = %u", (unsigned)g_frames_per_upload);
        }
    }

    /* --- jpeg_quality → camera sensor --- */
    item = cJSON_GetObjectItem(node, "jpeg_quality");
    if (parse_int(item, &ival)) {
        mqtt_cmd_msg_t cmd = {0};
        cmd.cmd = MQTT_CMD_CAMERA_QUALITY;
        cmd.payload.quality.quality = ival;
        xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
        ESP_LOGI(TAG, "jpeg_quality = %d", ival);
    }

    /* --- resolution --- */
    item = cJSON_GetObjectItem(node, "resolution");
    if (parse_int(item, &ival)) {
        mqtt_cmd_msg_t cmd = {0};
        cmd.cmd = MQTT_CMD_CAMERA_RESOLUTION;
        cmd.payload.resolution.framesize = ival;
        xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
        ESP_LOGI(TAG, "resolution = %d", ival);
    }

    /* --- reboot --- */
    item = cJSON_GetObjectItem(node, "reboot");
    if (parse_bool(item, &bval) && bval && !s_reboot_pending) {
        s_reboot_pending = true;
        pub_attr_bool("reboot", false);
        vTaskDelay(pdMS_TO_TICKS(300));
        esp_restart();
    }

    /* --- factory_reset / reset --- */
    item = cJSON_GetObjectItem(node, "factory_reset");
    if (!item) item = cJSON_GetObjectItem(node, "reset");
    if (parse_bool(item, &bval) && bval && !s_factory_reset_pending) {
        s_factory_reset_pending = true;
        pub_attr_bool("factory_reset", false);
        ESP_LOGW(TAG, "Factory reset được yêu cầu");
        vTaskDelay(pdMS_TO_TICKS(300));
        app_config_clear();
        esp_restart();
    }

    /* --- OTA qua fw_title + fw_version (ThingsBoard OTA flow) --- */
    const cJSON *fw_title   = cJSON_GetObjectItem(node, "fw_title");
    const cJSON *fw_version = cJSON_GetObjectItem(node, "fw_version");
    if (fw_title && cJSON_IsString(fw_title) &&
        fw_version && cJSON_IsString(fw_version)) {
        const char *title   = fw_title->valuestring;
        const char *version = fw_version->valuestring;
        const esp_app_desc_t *app = esp_app_get_description();
        if (app && strcmp(app->version, version) == 0) {
            ESP_LOGI(TAG, "Firmware đã là version %s, bỏ qua OTA", version);
        } else if (!s_ota_active &&
                   (strcmp(s_last_fw_title,   title)   != 0 ||
                    strcmp(s_last_fw_version, version) != 0)) {
            strncpy(s_last_fw_title,   title,   sizeof(s_last_fw_title)-1);
            strncpy(s_last_fw_version, version, sizeof(s_last_fw_version)-1);
            /* Xây URL download firmware từ TB */
            char ota_url[300];
            snprintf(ota_url, sizeof(ota_url),
                     THINGSBOARD_BASE_URL "/api/v1/%s/firmware?title=%s&version=%s",
                     s_token, title, version);
            ESP_LOGI(TAG, "OTA qua TB OTA: %s v%s", title, version);
            start_ota(ota_url);
        }
    }

    /* --- OTA qua ota_url / fw_url thuộc tính trực tiếp --- */
    const cJSON *ota_url = cJSON_GetObjectItem(node, "ota_url");
    if (!ota_url) ota_url = cJSON_GetObjectItem(node, "fw_url");
    if (ota_url && cJSON_IsString(ota_url) && ota_url->valuestring[0] &&
        !s_ota_active &&
        strcmp(s_last_ota_url, ota_url->valuestring) != 0) {
        ESP_LOGI(TAG, "OTA qua attribute URL: %s", ota_url->valuestring);
        start_ota(ota_url->valuestring);
    }

    /* ---- Đèn giao thông: timing override từ shared attrs ---- */
    uint32_t tl_r = 0, tl_y = 0, tl_g = 0;
    item = cJSON_GetObjectItem(node, "tl_red_ms");
    if (parse_int(item, &ival) && ival > 0) tl_r = (uint32_t)ival;
    item = cJSON_GetObjectItem(node, "tl_yellow_ms");
    if (parse_int(item, &ival) && ival > 0) tl_y = (uint32_t)ival;
    item = cJSON_GetObjectItem(node, "tl_green_ms");
    if (parse_int(item, &ival) && ival > 0) tl_g = (uint32_t)ival;
    if (tl_r || tl_y || tl_g)
        traffic_light_set_timings(tl_r, tl_y, tl_g);

    /* --- tl_mode: 0=normal, 1=emergency_red, 2=emergency_green --- */
    item = cJSON_GetObjectItem(node, "tl_mode");
    if (parse_int(item, &ival))
        traffic_light_set_mode((tl_mode_t)ival);

    cJSON_Delete(root);
}

/* ---------- RPC handler ---------- */

static void handle_rpc(const char *topic, const char *data, int len)
{
    int req_id = extract_rpc_id(topic);
    if (req_id < 0) return;

    cJSON *json   = cJSON_ParseWithLength(data, len);
    if (!json) { mqtt_app_send_rpc_response(req_id, false, "JSON lỗi"); return; }

    cJSON *method = cJSON_GetObjectItem(json, "method");
    cJSON *params = cJSON_GetObjectItem(json, "params");
    if (!method || !cJSON_IsString(method)) {
        mqtt_app_send_rpc_response(req_id, false, "Thiếu method");
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
        } else { mqtt_app_send_rpc_response(req_id, false, "Thiếu framesize"); }
    }
    else if (!strcmp(m, "setQuality")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "quality") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAMERA_QUALITY;
            cmd.payload.quality.quality = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "Thiếu quality"); }
    }
    else if (!strcmp(m, "setInterval")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "interval_ms") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAPTURE_INTERVAL;
            cmd.payload.interval.interval_ms = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "Thiếu interval_ms"); }
    }
    else if (!strcmp(m, "reboot")) {
        mqtt_app_send_rpc_response(req_id, true, "Đang khởi động lại...");
        vTaskDelay(pdMS_TO_TICKS(500));
        esp_restart();
    }
    else if (!strcmp(m, "startOTA")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "url") : NULL;
        if (p && cJSON_IsString(p)) {
            mqtt_app_send_rpc_response(req_id, true, "OTA bắt đầu");
            start_ota(p->valuestring);
        } else { mqtt_app_send_rpc_response(req_id, false, "Thiếu url"); }
    }
    else if (!strcmp(m, "getStatus")) {
        char st[300];
        snprintf(st, sizeof(st),
                 "{\"frames\":%lu,\"ok\":%lu,\"fail\":%lu,"
                 "\"heap\":%lu,\"interval\":%lu,\"camera\":%s,"
                 "\"rssi\":%d}",
                 (unsigned long)g_frame_count,
                 (unsigned long)g_send_success,
                 (unsigned long)g_send_fail,
                 (unsigned long)esp_get_free_heap_size(),
                 (unsigned long)g_capture_interval_ms,
                 g_camera_ok ? "true" : "false",
                 (int)get_wifi_rssi());
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
            mqtt_app_send_rpc_response(req_id, false, "Lỗi traffic_light");
        }
    }
    else if (!strcmp(m, "getTrafficStatus")) {
        tl_status_t st = traffic_light_get_status();
        const char *s  = (st.state == TL_STATE_RED)    ? "red" :
                         (st.state == TL_STATE_YELLOW)  ? "yellow" : "green";
        const char *md = (st.mode  == TL_MODE_NORMAL)          ? "normal" :
                         (st.mode  == TL_MODE_EMERGENCY_RED)    ? "emergency_red" :
                                                                   "emergency_green";
        char resp[200];
        snprintf(resp, sizeof(resp),
                 "{\"traffic_light_state\":\"%s\",\"operation_mode\":\"%s\","
                 "\"state_ms\":%lu}",
                 s, md, (unsigned long)st.state_ms);
        mqtt_app_send_rpc_response(req_id, true, resp);
    }
    else {
        ESP_LOGW(TAG, "RPC không biết: %s", m);
        mqtt_app_send_rpc_response(req_id, false, "Method không hỗ trợ");
    }

    if (enqueue && g_mqtt_cmd_queue) {
        xQueueSend(g_mqtt_cmd_queue, &cmd, pdMS_TO_TICKS(100));
    }
    cJSON_Delete(json);
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
        ESP_LOGI(TAG, "MQTT đã kết nối ThingsBoard");

        /* Subscribe */
        esp_mqtt_client_subscribe(ev->client, TB_TOPIC_RPC_REQUEST,  1);
        esp_mqtt_client_subscribe(ev->client, TB_TOPIC_ATTRIBUTES,    1);

        /* Yêu cầu shared attributes */
        esp_mqtt_client_publish(ev->client, TB_TOPIC_ATTRIBUTES_REQ,
            "{\"sharedKeys\":\"save_img,camera_id,cam_id,frames_per_upload,"
            "reboot,factory_reset,reset,ota_url,fw_url,fw_title,fw_version,"
            "jpeg_quality,resolution,active,inactivityAlarmTime,pixel_format,"
            "tl_red_ms,tl_yellow_ms,tl_green_ms,tl_mode\"}",
            0, 1, 0);

        /* Publish online status */
        esp_mqtt_client_publish(ev->client, TB_TOPIC_TELEMETRY,
                                "{\"status\":\"online\"}", 0, 1, 0);

        /* Client attributes: Model, fw_version, camera_id, mac */
        uint8_t mac[6] = {0};
        esp_read_mac(mac, ESP_MAC_WIFI_STA);
        const esp_app_desc_t *app = esp_app_get_description();
        char attrs[350];
        snprintf(attrs, sizeof(attrs),
                 "{\"Model\":\"GOOUUU Tech ESP32-S3-CAM N16R8\","
                 "\"fw_version\":\"%s\","
                 "\"camera_id\":%d,"
                 "\"mac\":\"%02X:%02X:%02X:%02X:%02X:%02X\","
                 "\"idf_ver\":\"%s\"}",
                 app ? app->version : "unknown",
                 g_camera_id,
                 mac[0],mac[1],mac[2],mac[3],mac[4],mac[5],
                 app ? app->idf_ver : "unknown");
        esp_mqtt_client_publish(ev->client, TB_TOPIC_ATTRIBUTES, attrs, 0, 1, 0);
        break;
    }

    case MQTT_EVENT_DISCONNECTED:
        s_connected = false;
        if (s_disconnect_tick == 0) s_disconnect_tick = xTaskGetTickCount();
        ESP_LOGW(TAG, "MQTT mất kết nối");
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
        ESP_LOGE(TAG, "MQTT lỗi");
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
        ESP_LOGI(TAG, "MQTT đã khởi tạo → %s", MQTT_BROKER_URI);
}

void mqtt_app_start(const char *token) { mqtt_app_init(token); }

bool mqtt_app_is_connected(void) { return s_connected; }

void mqtt_app_send_rpc_response(int req_id, bool success, const char *msg)
{
    if (!s_client || !s_connected || req_id < 0) return;
    char topic[80];
    snprintf(topic, sizeof(topic), "%s%d", RPC_RESP_PFX, req_id);
    char payload[512];
    if (msg && msg[0] == '{')
        snprintf(payload, sizeof(payload), "%s", msg);
    else
        snprintf(payload, sizeof(payload),
                 "{\"success\":%s,\"msg\":\"%s\"}",
                 success ? "true" : "false", msg ? msg : "");
    esp_mqtt_client_publish(s_client, topic, payload, 0, 1, 0);
}

void mqtt_app_publish_telemetry(const telemetry_msg_t *t)
{
    if (!s_client || !s_connected || !t) return;
    char buf[600];

    switch (t->type) {
    case TELEMETRY_HEALTH: {
        const health_telemetry_t *h = &t->data.health;
        snprintf(buf, sizeof(buf),
                 "{\"free_heap\":%lu,\"min_free_heap\":%lu,"
                 "\"Wifi_Status\":%d,\"frame_count\":%lu,"
                 "\"send_success\":%lu,\"send_fail\":%lu,"
                 "\"uptime_sec\":%lu,\"camera_ok\":%s,"
                 "\"mqtt_connected\":%s,\"net_error\":%s,"
                 "\"upload_ok\":%s,\"last_http_code\":%d,"
                 "\"latency_ms\":%lu}",
                 (unsigned long)h->free_heap,
                 (unsigned long)h->min_free_heap,
                 (int)h->wifi_rssi,
                 (unsigned long)h->frame_count,
                 (unsigned long)h->send_success,
                 (unsigned long)h->send_fail,
                 (unsigned long)h->uptime_sec,
                 h->camera_ok      ? "true" : "false",
                 h->mqtt_connected ? "true" : "false",
                 h->net_error      ? "true" : "false",
                 h->upload_ok      ? "true" : "false",
                 h->last_http_code,
                 (unsigned long)h->latency_ms);
        break;
    }
    case TELEMETRY_STATUS:
        snprintf(buf, sizeof(buf), "{\"status\":\"%s\"}", t->data.status.status);
        break;
    case TELEMETRY_EVENT:
        /* key/value pair — publish như {key: value} */
        snprintf(buf, sizeof(buf), "{\"%s\":\"%s\"}",
                 t->data.event.key[0] ? t->data.event.key : "event",
                 t->data.event.value);
        break;
    case TELEMETRY_TRAFFIC_LIGHT: {
        static const char *tl_states[] = { "red", "yellow", "green" };
        static const char *tl_modes[]  = { "normal", "emergency_red", "emergency_green" };
        const tl_telemetry_t *tl = &t->data.traffic;
        uint8_t si = tl->state < 3 ? tl->state : 0;
        uint8_t mi = tl->mode  < 3 ? tl->mode  : 0;
        snprintf(buf, sizeof(buf),
                 "{\"traffic_light_state\":\"%s\","
                 "\"operation_mode\":\"%s\","
                 "\"tl_state_ms\":%lu}",
                 tl_states[si], tl_modes[mi],
                 (unsigned long)tl->state_ms);
        break;
    }
    default: return;
    }

    esp_mqtt_client_publish(s_client, TB_TOPIC_TELEMETRY, buf, 0, 1, 0);
}

/* ---------- MQTT task ---------- */

void mqtt_task(void *pvParameter)
{
    const char *init_token = (const char *)pvParameter;
    telemetry_msg_t telem;

    ESP_LOGI(TAG, "MQTT task khởi động");

    /* Đọc config để re-provision nếu cần */
    app_config_state_t state;
    if (app_config_load(&s_cfg, &state) != ESP_OK)
        app_config_set_defaults(&s_cfg);

    /* Kết nối MQTT với token có sẵn hoặc thử provision */
    if (init_token && init_token[0]) {
        mqtt_app_init(init_token);
    } else {
        ESP_LOGW(TAG, "Không có token — sẽ thử provisioning");
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

        /* Lấy telemetry từ queue và publish */
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
    ESP_LOGI(TAG, "MQTT task kết thúc");
    vTaskDelete(NULL);
}
