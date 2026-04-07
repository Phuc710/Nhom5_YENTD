/*
 * mqtt_app.c - MQTT client for ThingsBoard/Mosquitto synchronization.
 * Handles telemetry, attributes, RPC, and OTA updates.
 */
#include "mqtt_app.h"
#include "backend_sync.h"
#include "task_manager.h"
#include "tb_provisioning.h"
#include "app_config.h"
#include "goouuu_camera.h"
/* traffic_light.h removed — traffic light moved to ESP32_PCB */
#include "wifi_manager.h"
#include "esp_camera.h"
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

static const char *TAG = "mqtt";

#define RPC_RESP_PFX "v1/devices/me/rpc/response/"

/* Attribute validation ranges */
#define CAPTURE_INTERVAL_MIN_MS   100
#define CAPTURE_INTERVAL_MAX_MS   3600000
#define JPEG_QUALITY_MIN          4
#define JPEG_QUALITY_MAX          63
#define TELEMETRY_INTERVAL_MIN_MS 5000
#define TELEMETRY_INTERVAL_MAX_MS 3600000
/* TL_DURATION defines removed — traffic light timing handled by ESP32_PCB */

#ifndef REPROV_RETRY_MS
#define REPROV_RETRY_MS 3000
#endif

static esp_mqtt_client_handle_t s_client      = NULL;
static esp_mqtt_client_handle_t s_mosquitto_client = NULL;
static bool                     s_mosquitto_connected = false;
static bool                     s_connected   = false;
static bool                     s_initialized = false;
static char                     s_token[128]  = {0};
static char                     s_last_ota_url[256] = {0};
static bool                     s_ota_active        = false;
static bool                     s_reboot_pending    = false;
static bool                     s_reprovision_pending = false;
static bool                     s_factory_reset_pending = false;
static app_config_t             s_cfg;

bool mqtt_app_is_degraded(void)
{
    return backend_sync_is_degraded();
}

static bool parse_bool(const cJSON *item, bool *out)
{
    if (!item || !out) return false;
    if (cJSON_IsBool(item))   { *out = cJSON_IsTrue(item);            return true; }
    if (cJSON_IsNumber(item)) { *out = (item->valuedouble != 0);      return true; }
    if (cJSON_IsString(item)) {
        if (!strcmp(item->valuestring, "true")  || !strcmp(item->valuestring, "1"))
            { *out = true;  return true; }
        if (!strcmp(item->valuestring, "false") || !strcmp(item->valuestring, "0"))
            { *out = false; return true; }
    }
    return false;
}

static bool parse_int(const cJSON *item, int *out)
{
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
    if (parse_int(item, out)) return true;
    if (!item || !out || !cJSON_IsString(item) ||
        !item->valuestring || !item->valuestring[0]) return false;
    framesize_t fs = FRAMESIZE_INVALID;
    if (!goouuu_camera_parse_framesize(item->valuestring, &fs)) return false;
    *out = (int)fs;
    return true;
}

static bool parse_non_empty_string(const cJSON *item, const char **out)
{
    if (!item || !out || !cJSON_IsString(item) ||
        !item->valuestring || !item->valuestring[0]) return false;
    *out = item->valuestring;
    return true;
}

static const char *get_reset_reason_str(void)
{
    switch (esp_reset_reason()) {
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

static const char *get_device_state_str(void)
{
    if (s_ota_active) return "ota";
    if (!g_camera_ok) return "error";
    if (backend_sync_is_degraded()) return "degraded";
    return device_state_to_str(task_manager_get_device_state());
}

static const char *get_resolution_label(void)
{
    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) {
        const char *label = goouuu_camera_framesize_to_string(
            (framesize_t)sensor->status.framesize);
        if (label && label[0]) return label;
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

static void pub_attr_bool(const char *key, bool val)
{
    if (!s_client || !s_connected) return;
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"%s\":%s}", key, val ? "true" : "false");
    esp_mqtt_client_publish(s_client, TB_TOPIC_ATTRIBUTES, buf, 0, 1, 0);
}

static void pub_fw_state(const char *state, const char *err)
{
    if (!s_client || !s_connected) return;
    char buf[160];
    if (err && err[0])
        snprintf(buf, sizeof(buf), "{\"fw_state\":\"%s\",\"fw_error\":\"%s\"}", state, err);
    else
        snprintf(buf, sizeof(buf), "{\"fw_state\":\"%s\"}", state);
    esp_mqtt_client_publish(s_client, TB_TOPIC_ATTRIBUTES, buf, 0, 1, 0);
}

static void publish_client_attributes(void)
{
    if (!s_client || !s_connected) return;

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    char ip[20]           = {0};
    char stream_url[64]   = {0};
    char device_name[64]  = {0};
    char tb_dev_name[48]  = {0};
    char mac_str[18]      = {0};

    bool has_ip = wifi_get_ip_string(ip, sizeof(ip));
    if (has_ip) snprintf(stream_url, sizeof(stream_url), "http://%s:81/stream", ip);

    if (s_cfg.device_name[0]) {
        snprintf(device_name,  sizeof(device_name),  "%s", s_cfg.device_name);
        snprintf(tb_dev_name,  sizeof(tb_dev_name),  "%s", s_cfg.device_name);
    } else {
        snprintf(tb_dev_name,  sizeof(tb_dev_name),
                 "cam-%02X%02X%02X%02X%02X%02X",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
        snprintf(device_name, sizeof(device_name), "%s", tb_dev_name);
    }
    snprintf(mac_str, sizeof(mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    const esp_app_desc_t *app = esp_app_get_description();

    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    cJSON_AddStringToObject(root, "device_model",    BACKEND_SYNC_DEVICE_MODEL);
    cJSON_AddStringToObject(root, "device_name",     device_name);
    cJSON_AddStringToObject(root, "tb_device_name",  tb_dev_name);
    cJSON_AddStringToObject(root, "mac_address",     mac_str);
    cJSON_AddStringToObject(root, "fw_version",      app ? app->version : "unknown");
    cJSON_AddStringToObject(root, "idf_ver",         app ? app->idf_ver : "unknown");
    cJSON_AddStringToObject(root, "location",        s_cfg.location);
    cJSON_AddStringToObject(root, "reset_reason",    get_reset_reason_str());
    cJSON_AddStringToObject(root, "wifi_ssid",       s_cfg.ssid);
    cJSON_AddStringToObject(root, "resolution",      get_resolution_label());
    cJSON_AddStringToObject(root, "ip_address",      has_ip ? ip : "");
    cJSON_AddStringToObject(root, "stream_url",      has_ip ? stream_url : "");
    cJSON_AddStringToObject(root, "stream_scheme",   "http");
    cJSON_AddStringToObject(root, "stream_host",     has_ip ? ip : "");
    cJSON_AddNumberToObject(root, "stream_port",     81);
    cJSON_AddStringToObject(root, "stream_path",     "/stream");
    cJSON_AddStringToObject(root, "stream_snapshot_path", "/snapshot");
    cJSON_AddStringToObject(root, "backend_url",     BACKEND_UPLOAD_URL);
    cJSON_AddStringToObject(root, "device_state",    get_device_state_str());
    cJSON_AddStringToObject(root, "backend_sync",    backend_sync_get_state_str());

    char *payload = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (payload) {
        esp_mqtt_client_publish(s_client, TB_TOPIC_ATTRIBUTES, payload, 0, 1, 0);
        free(payload);
    }
}

static void ota_task(void *pv)
{
    char *url = (char *)pv;
    if (!url) { s_ota_active = false; vTaskDelete(NULL); return; }

    ESP_LOGI(TAG, "ota: start %s", url);
    pub_fw_state("DOWNLOADING", NULL);

    esp_http_client_config_t hcfg = {
        .url        = url,
        .timeout_ms = 30000,
    };
    if (strncmp(url, "https", 5) == 0) hcfg.crt_bundle_attach = esp_crt_bundle_attach;

    esp_https_ota_config_t ocfg = { .http_config = &hcfg };
    esp_err_t ret = esp_https_ota(&ocfg);

    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "ota: done, rebooting");
        pub_fw_state("UPDATED", NULL);
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    } else {
        ESP_LOGE(TAG, "ota: failed %s", esp_err_to_name(ret));
        pub_fw_state("FAILED", esp_err_to_name(ret));
        vTaskDelay(pdMS_TO_TICKS(2000));
    }

    free(url);
    s_ota_active = false;
    vTaskDelete(NULL);
}

static void start_ota(const char *url)
{
    if (!url || !url[0]) return;
    if (s_ota_active) { ESP_LOGW(TAG, "ota: already in progress"); return; }

    strncpy(s_last_ota_url, url, sizeof(s_last_ota_url) - 1);
    s_ota_active = true;

    char *copy = strdup(url);
    if (!copy || xTaskCreate(ota_task, "ota", 8192, copy, 3, NULL) != pdPASS) {
        free(copy);
        s_ota_active = false;
        ESP_LOGE(TAG, "ota: task create failed");
    }
}

static void trigger_reprovision_restart(const char *src)
{
    ESP_LOGW(TAG, "reprov: clearing token (%s)", src ? src : "?");
    if (app_config_clear_token() != ESP_OK) return;
    s_cfg.token[0] = '\0';
    s_token[0]     = '\0';
    pub_attr_bool("reprovision", false);
    vTaskDelay(pdMS_TO_TICKS(300));
    esp_restart();
}

static void handle_attributes(const char *data, int len)
{
    cJSON *root = cJSON_ParseWithLength(data, len);
    if (!root) { ESP_LOGW(TAG, "attr: json parse error"); return; }

    cJSON *node = cJSON_GetObjectItem(root, "shared");
    if (!node || !cJSON_IsObject(node)) node = root;

    const cJSON *item;
    bool bval;
    int ival;
    const char *ota_url_val = NULL;
    const esp_app_desc_t *app = esp_app_get_description();

    /* capture_interval_ms */
    item = cJSON_GetObjectItem(node, "capture_interval_ms");
    if (parse_int(item, &ival)) {
        if (ival < CAPTURE_INTERVAL_MIN_MS || ival > CAPTURE_INTERVAL_MAX_MS) {
            ESP_LOGW(TAG, "attr: invalid capture_interval_ms=%d", ival);
        } else if (g_mqtt_cmd_queue) {
            mqtt_cmd_msg_t cmd = {0};
            cmd.cmd = MQTT_CMD_CAPTURE_INTERVAL;
            cmd.payload.interval.interval_ms = ival;
            xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
            ESP_LOGD(TAG, "attr: capture_interval=%dms", ival);
        }
    }

    /* jpeg_quality */
    item = cJSON_GetObjectItem(node, "jpeg_quality");
    if (parse_int(item, &ival)) {
        if (ival < JPEG_QUALITY_MIN || ival > JPEG_QUALITY_MAX) {
            ESP_LOGW(TAG, "attr: invalid jpeg_quality=%d", ival);
        } else if (g_mqtt_cmd_queue && is_quality_change_needed(ival)) {
            mqtt_cmd_msg_t cmd = {0};
            cmd.cmd = MQTT_CMD_CAMERA_QUALITY;
            cmd.payload.quality.quality = ival;
            xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
            ESP_LOGD(TAG, "attr: jpeg_quality=%d", ival);
        }
    }

    /* resolution */
    item = cJSON_GetObjectItem(node, "resolution");
    if (parse_resolution_framesize(item, &ival)) {
        if (g_mqtt_cmd_queue && is_resolution_change_needed(ival)) {
            mqtt_cmd_msg_t cmd = {0};
            cmd.cmd = MQTT_CMD_CAMERA_RESOLUTION;
            cmd.payload.resolution.framesize = ival;
            xQueueSend(g_mqtt_cmd_queue, &cmd, 0);
            ESP_LOGD(TAG, "attr: resolution=%d", ival);
        }
    }

    /* reboot */
    item = cJSON_GetObjectItem(node, "reboot");
    if (parse_bool(item, &bval) && bval && !s_reboot_pending) {
        s_reboot_pending = true;
        pub_attr_bool("reboot", false);
        vTaskDelay(pdMS_TO_TICKS(300));
        esp_restart();
    }

    /* factory_reset */
    item = cJSON_GetObjectItem(node, "factory_reset");
    if (parse_bool(item, &bval) && bval && !s_factory_reset_pending) {
        s_factory_reset_pending = true;
        pub_attr_bool("factory_reset", false);
        ESP_LOGW(TAG, "attr: factory reset");
        vTaskDelay(pdMS_TO_TICKS(300));
        app_config_clear();
        esp_restart();
    }

    /* ota_url + target_fw_version */
    item = cJSON_GetObjectItem(node, "ota_url");
    parse_non_empty_string(item, &ota_url_val);

    const cJSON *target_fw = cJSON_GetObjectItem(node, "target_fw_version");
    if (target_fw && cJSON_IsString(target_fw) && target_fw->valuestring[0]) {
        if (app && strcmp(app->version, target_fw->valuestring) == 0) {
            ESP_LOGD(TAG, "ota: fw matches %s", target_fw->valuestring);
        } else if (ota_url_val && !s_ota_active &&
                   strcmp(s_last_ota_url, ota_url_val) != 0) {
            ESP_LOGI(TAG, "ota: trigger v%s", target_fw->valuestring);
            start_ota(ota_url_val);
        }
    } else if (ota_url_val && !s_ota_active &&
               strcmp(s_last_ota_url, ota_url_val) != 0) {
        start_ota(ota_url_val);
    }

    /* Traffic light timings removed — controlled by ESP32_PCB via MQTT */

    /* telemetry_interval_ms */
    item = cJSON_GetObjectItem(node, "telemetry_interval_ms");
    if (parse_int(item, &ival)) {
        if (ival >= TELEMETRY_INTERVAL_MIN_MS && ival <= TELEMETRY_INTERVAL_MAX_MS) {
            g_telemetry_interval_ms = (uint32_t)ival;
            ESP_LOGD(TAG, "attr: telemetry_interval=%dms", ival);
        } else {
            ESP_LOGW(TAG, "attr: invalid telemetry_interval=%d", ival);
        }
    }

    cJSON_Delete(root);
}

static int extract_rpc_id(const char *topic)
{
    const char *p = strrchr(topic, '/');
    return (p && *(p + 1)) ? atoi(p + 1) : -1;
}

static void handle_rpc(const char *topic, const char *data, int len)
{
    int req_id = extract_rpc_id(topic);
    if (req_id < 0) return;

    cJSON *json = cJSON_ParseWithLength(data, len);
    if (!json) { mqtt_app_send_rpc_response(req_id, false, "json error"); return; }

    cJSON *method = cJSON_GetObjectItem(json, "method");
    cJSON *params = cJSON_GetObjectItem(json, "params");
    if (!method || !cJSON_IsString(method)) {
        mqtt_app_send_rpc_response(req_id, false, "missing method");
        cJSON_Delete(json); return;
    }

    const char *m = method->valuestring;
    ESP_LOGI(TAG, "rpc[%d] %s", req_id, m);

    mqtt_cmd_msg_t cmd  = {0};
    cmd.request_id      = req_id;
    bool enqueue        = false;

    if (!strcmp(m, "setResolution")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "framesize") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAMERA_RESOLUTION;
            cmd.payload.resolution.framesize = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "missing framesize"); }
    }
    else if (!strcmp(m, "setQuality")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "quality") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAMERA_QUALITY;
            cmd.payload.quality.quality = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "missing quality"); }
    }
    else if (!strcmp(m, "setInterval")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "interval_ms") : NULL;
        if (p && cJSON_IsNumber(p)) {
            cmd.cmd = MQTT_CMD_CAPTURE_INTERVAL;
            cmd.payload.interval.interval_ms = p->valueint;
            enqueue = true;
            mqtt_app_send_rpc_response(req_id, true, "OK");
        } else { mqtt_app_send_rpc_response(req_id, false, "missing interval_ms"); }
    }
    else if (!strcmp(m, "reboot")) {
        mqtt_app_send_rpc_response(req_id, true, "rebooting...");
        vTaskDelay(pdMS_TO_TICKS(500));
        esp_restart();
    }
    else if (!strcmp(m, "reprovision")) {
        mqtt_app_send_rpc_response(req_id, true, "clearing old token...");
        s_reprovision_pending = true;
        vTaskDelay(pdMS_TO_TICKS(300));
        trigger_reprovision_restart("rpc");
    }
    else if (!strcmp(m, "startOTA")) {
        cJSON *p = params ? cJSON_GetObjectItem(params, "url") : NULL;
        if (p && cJSON_IsString(p)) {
            mqtt_app_send_rpc_response(req_id, true, "ota starting");
            start_ota(p->valuestring);
        } else { mqtt_app_send_rpc_response(req_id, false, "missing url"); }
    }
    else if (!strcmp(m, "getStatus")) {
        char ip[20] = {0};
        char stream_url[64] = {0};
        bool has_ip = wifi_get_ip_string(ip, sizeof(ip));
        if (has_ip) snprintf(stream_url, sizeof(stream_url), "http://%s:81/stream", ip);
        char st[256];
        snprintf(st, sizeof(st),
                 "{\"status\":\"running\",\"backend_url\":\"%s\","
                 "\"backend_sync\":\"%s\",\"device_state\":\"%s\"}",
                 BACKEND_UPLOAD_URL,
                 backend_sync_get_state_str(),
                 get_device_state_str());
        mqtt_app_send_rpc_response(req_id, true, st);
    }
    else if (!strcmp(m, "factoryReset")) {
        mqtt_app_send_rpc_response(req_id, true, "factory reset...");
        vTaskDelay(pdMS_TO_TICKS(300));
        app_config_clear();
        esp_restart();
    }
    /* setNormalMode / setEmergencyRed / setEmergencyGreen / getTrafficStatus
     * removed — traffic light is now controlled by ESP32_PCB via MQTT.
     * Backend publishes to KAI/pcb/{device_name}/cmd directly. */
    else {
        ESP_LOGW(TAG, "rpc: unknown method=%s", m);
        mqtt_app_send_rpc_response(req_id, false, "method not supported");
    }

    if (enqueue && g_mqtt_cmd_queue) {
        xQueueSend(g_mqtt_cmd_queue, &cmd, pdMS_TO_TICKS(100));
    }
    cJSON_Delete(json);
}

static void mqtt_evt_handler(void *arg, esp_event_base_t base, int32_t id, void *edata)
{
    (void)arg;
    (void)base;
    esp_mqtt_event_handle_t ev = (esp_mqtt_event_handle_t)edata;

    switch (id) {
    case MQTT_EVENT_CONNECTED: {
        s_connected = true;
        ESP_LOGI(TAG, "tb: connected");
        task_manager_set_device_state(DEVICE_STATE_MQTT_READY);

        esp_mqtt_client_subscribe(ev->client, TB_TOPIC_RPC_REQUEST, 1);
        esp_mqtt_client_subscribe(ev->client, TB_TOPIC_ATTRIBUTES,  1);

        esp_mqtt_client_publish(ev->client, TB_TOPIC_ATTRIBUTES_REQ,
            "{\"sharedKeys\":\"capture_interval_ms,jpeg_quality,resolution,"
            "reboot,factory_reset,ota_url,target_fw_version,telemetry_interval_ms\"}",
            0, 1, 0);
        /* tl_red_ms/tl_yellow_ms/tl_green_ms removed — traffic light on ESP32_PCB */

        publish_client_attributes();

        backend_sync_set_token(s_token);
        backend_sync_update_config(&s_cfg);
        backend_sync_start(&s_cfg, s_token);
        /* Chỉ notify ngay nếu stream đã sẵn sàng (MQTT reconnect).
         * Fresh boot: main.c sẽ notify sau stream_server_start(). */
        if (task_manager_get_device_state() >= DEVICE_STATE_STREAM_READY) {
            backend_sync_notify();
        }
        task_manager_set_device_state(DEVICE_STATE_BACKEND_SYNCING);
        break;
    }
    case MQTT_EVENT_DISCONNECTED:
        s_connected = false;
        task_manager_set_system_ready(false);
        task_manager_set_device_state(DEVICE_STATE_RECONNECTING);
        ESP_LOGW(TAG, "tb: disconnected");
        break;
    case MQTT_EVENT_DATA:
        if (ev->topic_len > 0 && ev->data_len > 0) {
            char *topic = strndup(ev->topic, ev->topic_len);
            if (topic) {
                if      (strstr(topic, "rpc/request/")) handle_rpc(topic, ev->data, ev->data_len);
                else if (strstr(topic, "attributes"))   handle_attributes(ev->data, ev->data_len);
                free(topic);
            }
        }
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "tb: error");
        break;
    default: break;
    }
}

static void mosquitto_evt_handler(void *arg, esp_event_base_t base, int32_t id, void *edata)
{
    (void)arg; (void)base;
    esp_mqtt_event_handle_t ev = (esp_mqtt_event_handle_t)edata;

    switch (id) {
    case MQTT_EVENT_CONNECTED: {
        s_mosquitto_connected = true;
        ESP_LOGI(TAG, "mosq: connected");
        /* Camera không subscribe /cmd nữa — traffic light commands đi thẳng tới ESP32_PCB.
         * Camera chỉ dùng Mosquitto để publish telemetry. */
        break;
    }
    case MQTT_EVENT_DISCONNECTED:
        s_mosquitto_connected = false;
        ESP_LOGW(TAG, "mosq: disconnected");
        break;

    case MQTT_EVENT_DATA: {
        /* Camera chỉ nhận telemetry từ Mosquitto.
         * Traffic light commands (KAI/pcb/+/cmd) đi thẳng đến ESP32_PCB —
         * camera không xử lý nữa. */
        if (ev->topic_len > 0 && ev->data_len > 0) {
            ESP_LOGD(TAG, "mosq: data on topic (ignored by camera)");
        }
        break;
    }
    default: break;
    }
}

static bool mosquitto_client_create(void)
{
    if (s_mosquitto_client) {
        esp_mqtt_client_stop(s_mosquitto_client);
        esp_mqtt_client_destroy(s_mosquitto_client);
        s_mosquitto_client = NULL;
        s_mosquitto_connected = false;
    }
#ifdef MOSQUITTO_URI
    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = MOSQUITTO_URI,
        .session.keepalive  = 30,
    };
    s_mosquitto_client = esp_mqtt_client_init(&cfg);
    if (!s_mosquitto_client) { ESP_LOGE(TAG, "mosq: init failed"); return false; }
    esp_mqtt_client_register_event(s_mosquitto_client, ESP_EVENT_ANY_ID, mosquitto_evt_handler, NULL);
    if (esp_mqtt_client_start(s_mosquitto_client) != ESP_OK) {
        ESP_LOGE(TAG, "mosq: start failed");
        esp_mqtt_client_destroy(s_mosquitto_client);
        s_mosquitto_client = NULL;
        return false;
    }
    return true;
#else
    return false;
#endif
}

static bool mqtt_client_create(const char *token)
{
    if (s_client) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
        s_client      = NULL;
        s_initialized = false;
        s_connected   = false;
    }
    if (!token || !token[0]) return false;

    strncpy(s_token, token, sizeof(s_token) - 1);
    backend_sync_set_token(token);

    esp_mqtt_client_config_t cfg = {
        .broker.address.uri   = MQTT_BROKER_URI,
        .credentials.username = s_token,
        .session.keepalive    = 30,
    };
    s_client = esp_mqtt_client_init(&cfg);
    if (!s_client) { ESP_LOGE(TAG, "tb: init failed"); return false; }
    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, mqtt_evt_handler, NULL);
    if (esp_mqtt_client_start(s_client) != ESP_OK) {
        ESP_LOGE(TAG, "tb: start failed");
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
        return false;
    }
    s_initialized = true;
    return true;
}

void mqtt_app_init(const char *token)
{
    if (s_initialized) return;
    if (!mqtt_client_create(token))
        ESP_LOGW(TAG, "tb: init failed (no token)");
    else
        ESP_LOGI(TAG, "tb: connecting %s", MQTT_BROKER_URI);
    mosquitto_client_create();
    s_initialized = true;
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
    if (!task_manager_is_system_ready() && t->type != TELEMETRY_HEALTH) return;

    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    switch (t->type) {
    case TELEMETRY_HEALTH: {
        const health_telemetry_t *h = &t->data.health;
        const char *ls = (h->light_state == 0) ? "RED" : (h->light_state == 1) ? "YELLOW" : "GREEN";
        cJSON_AddNumberToObject(root, "free_heap",            h->free_heap);
        cJSON_AddNumberToObject(root, "min_free_heap",        h->min_free_heap);
        cJSON_AddNumberToObject(root, "wifi_rssi",            h->wifi_rssi);
        cJSON_AddNumberToObject(root, "uptime_s",             h->uptime_sec);
        cJSON_AddBoolToObject  (root, "camera_ok",            h->camera_ok);
        cJSON_AddBoolToObject  (root, "mqtt_connected",       h->mqtt_connected);
        cJSON_AddBoolToObject  (root, "backend_degraded",     h->backend_degraded);
        cJSON_AddNumberToObject(root, "wifi_disconnect_count",h->wifi_disconnect_count);
        cJSON_AddStringToObject(root, "device_state",         h->device_state[0] ? h->device_state : "online");
        cJSON_AddNumberToObject(root, "last_seen_ts",         h->last_seen_ts);
        cJSON_AddStringToObject(root, "light_state",          ls);
        cJSON_AddNumberToObject(root, "cpu_temp",             h->cpu_temp);
        break;
    }
    case TELEMETRY_STATUS:
        cJSON_AddStringToObject(root, "status", t->data.status.status);
        break;
    case TELEMETRY_EVENT:
        cJSON_AddStringToObject(root, t->data.event.key[0] ? t->data.event.key : "event", t->data.event.value);
        break;
    /* TELEMETRY_TRAFFIC_LIGHT removed — traffic light telemetry
     * now comes from ESP32_PCB directly via KAI/pcb/{name}/telemetry */
    default:
        cJSON_Delete(root); return;
    }

    char *buf = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (buf) {
        esp_mqtt_client_publish(s_client, TB_TOPIC_TELEMETRY, buf, 0, 1, 0);
        if (s_mosquitto_client && s_mosquitto_connected && s_cfg.device_name[0] != '\0') {
            char mosq_topic[128];
            snprintf(mosq_topic, sizeof(mosq_topic), "KAI/cameras/%s/telemetry", s_cfg.device_name);
            esp_mqtt_client_publish(s_mosquitto_client, mosq_topic, buf, 0, 1, 0);
        }
        free(buf);
    }
}

void mqtt_app_notify_backend_synced(int camera_id, bool is_new)
{
    if (camera_id <= 0) return;
    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    cJSON_AddStringToObject(root, "event", "backend_synced");
    cJSON_AddNumberToObject(root, "camera_id", camera_id);
    cJSON_AddStringToObject(root, "sync_mode", is_new ? "new" : "reconnect");
    cJSON_AddStringToObject(root, "backend_sync", backend_sync_get_state_str());
    cJSON_AddStringToObject(root, "device_state", get_device_state_str());
    cJSON_AddBoolToObject(root, "system_ready", task_manager_is_system_ready());

    char *payload = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!payload) return;

    if (s_client && s_connected) {
        esp_mqtt_client_publish(s_client, TB_TOPIC_TELEMETRY, payload, 0, 1, 0);
    }
    if (s_mosquitto_client && s_mosquitto_connected && s_cfg.device_name[0] != '\0') {
        char topic[128];
        snprintf(topic, sizeof(topic), "KAI/cameras/%s/status", s_cfg.device_name);
        esp_mqtt_client_publish(s_mosquitto_client, topic, payload, 0, 1, 0);
    }
    free(payload);
}

void mqtt_task(void *pvParameter)
{
    const char *init_token = (const char *)pvParameter;
    telemetry_msg_t telem;

    ESP_LOGI(TAG, "task started");

    app_config_state_t state;
    if (app_config_load(&s_cfg, &state) != ESP_OK) app_config_set_defaults(&s_cfg);

    if (init_token && init_token[0]) {
        mqtt_app_init(init_token);
    } else {
        ESP_LOGW(TAG, "no token - waiting for prov");
    }

    TickType_t last_prov_tick = 0;
    int prov_attempts  = 0;

    while (g_system_running) {
        bool has_token = (init_token && init_token[0]) || tb_has_token(&s_cfg);

        if ((!s_initialized || !s_connected) && !has_token) {
            task_manager_set_device_state(DEVICE_STATE_PROVISIONING);
            TickType_t now = xTaskGetTickCount();
            if (last_prov_tick == 0 || (now - last_prov_tick) >= pdMS_TO_TICKS(REPROV_RETRY_MS)) {
                last_prov_tick = now;
                if (tb_has_prov_credentials(&s_cfg)) {
                    prov_attempts++;
                    ESP_LOGI(TAG, "prov: attempt %d", prov_attempts);
                    if (tb_provision_device(&s_cfg)) {
                        backend_sync_set_token(s_cfg.token);
                        backend_sync_update_config(&s_cfg);
                        task_manager_set_device_state(DEVICE_STATE_MQTT_CONNECTING);
                        mqtt_client_create(s_cfg.token);
                    } else {
                        vTaskDelay(pdMS_TO_TICKS(500));
                    }
                }
            }
        }

        while (xQueueReceive(g_telemetry_queue, &telem, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (telem.type == TELEMETRY_HEALTH) backend_sync_push_health(&telem.data.health);
            if (s_connected) mqtt_app_publish_telemetry(&telem);
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }

    if (s_client) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
    }
    backend_sync_stop();
    ESP_LOGI(TAG, "task stopped");
    vTaskDelete(NULL);
}
