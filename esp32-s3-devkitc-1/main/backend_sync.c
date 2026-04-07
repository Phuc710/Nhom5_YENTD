/*
 * backend_sync.c — Đồng bộ ESP32 với backend HTTP.
 *
 * Flow: MQTT connected → /provision → parse camera_id → NVS → synced
 * Retry mãi mỗi BACKEND_SYNC_RETRY_MS cho đến khi thành công.
 * Không block startup. Thiết bị chạy bình thường dù backend chưa online.
 */
#include "backend_sync.h"
#include "app_config.h"
#include "mqtt_app.h"
#include "task_manager.h"
#include "wifi_manager.h"

#include "cJSON.h"
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include <stdlib.h>
#include <string.h>

static const char *TAG = "backend_sync";

/* ─── State ─────────────────────────────────────────────────────────────── */
static TaskHandle_t      s_task   = NULL;
static SemaphoreHandle_t s_mtx   = NULL;

static app_config_t s_cfg;
static char         s_token[128];
static char         s_state[48] = "pending";
static int          s_assigned_id = -1;
static bool         s_synced      = false;
static bool         s_force_reprov = false;

/* ─── Helpers ─────────────────────────────────────────────────────────────── */
static void state_set(const char *s)
{
    snprintf(s_state, sizeof(s_state), "%s", s ? s : "?");
}

static bool lock(void)   { return s_mtx && xSemaphoreTake(s_mtx, pdMS_TO_TICKS(50)) == pdTRUE; }
static void unlock(void) { xSemaphoreGive(s_mtx); }

static void build_url(char *out, size_t n, const char *path)
{
    size_t bl = strlen(BACKEND_UPLOAD_URL);
    bool bs = bl && BACKEND_UPLOAD_URL[bl - 1] == '/';
    bool ps = path[0] == '/';
    if      (bs && ps)  snprintf(out, n, "%s%s", BACKEND_UPLOAD_URL, path + 1);
    else if (!bs && !ps) snprintf(out, n, "%s/%s", BACKEND_UPLOAD_URL, path);
    else                 snprintf(out, n, "%s%s",  BACKEND_UPLOAD_URL, path);
}

/* ─── HTTP response buffer ─────────────────────────────────────────────── */
static char   s_resp_buf[512];
static size_t s_resp_len;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    if (evt->event_id == HTTP_EVENT_ON_DATA && evt->data_len > 0) {
        size_t room = sizeof(s_resp_buf) - 1 - s_resp_len;
        size_t take = (size_t)evt->data_len < room ? (size_t)evt->data_len : room;
        if (take > 0) {
            memcpy(s_resp_buf + s_resp_len, evt->data, take);
            s_resp_len += take;
            s_resp_buf[s_resp_len] = '\0';
        }
    }
    return ESP_OK;
}

/* ─── Provision HTTP call ────────────────────────────────────────────────── */
static bool do_provision(const app_config_t *cfg, const char *tok)
{
    if (!cfg || !tok || !tok[0]) return false;

    uint8_t mac[6];
    char    mac_str[18], ip[20], stream_url[64], snap_url[64];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(mac_str, sizeof(mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    if (!wifi_get_ip_string(ip, sizeof(ip))) {
        ESP_LOGW(TAG, "[PROV] no IP");
        return false;
    }
    snprintf(stream_url, sizeof(stream_url), "http://%s:81/stream",    ip);
    snprintf(snap_url,   sizeof(snap_url),   "http://%s:81/snapshot",  ip);

    const char *dev = cfg->device_name[0] ? cfg->device_name : mac_str;
    const esp_app_desc_t *app_desc = esp_app_get_description();
    const char *proj = (app_desc && app_desc->project_name[0])
                     ? app_desc->project_name : BACKEND_SYNC_DEVICE_PREFIX;

    cJSON *j = cJSON_CreateObject();
    if (!j) return false;
    cJSON_AddNumberToObject(j, "camera_id",      cfg->camera_id);
    cJSON_AddStringToObject(j, "camera_name",    dev);
    cJSON_AddStringToObject(j, "tb_device_name", dev);
    cJSON_AddStringToObject(j, "device_name",    dev);
    cJSON_AddStringToObject(j, "project_name",   proj);
    cJSON_AddStringToObject(j, "device_model",   BACKEND_SYNC_DEVICE_MODEL);
    cJSON_AddStringToObject(j, "mac_address",    mac_str);
    cJSON_AddStringToObject(j, "ip_address",     ip);
    cJSON_AddStringToObject(j, "stream_url",     stream_url);
    cJSON_AddStringToObject(j, "snapshot_url",   snap_url);
    cJSON_AddStringToObject(j, "location",       cfg->location);
    cJSON_AddStringToObject(j, "wifi_ssid",      cfg->ssid);
    cJSON_AddStringToObject(j, "resolution",     "VGA");
    cJSON_AddStringToObject(j, "access_token",   tok);
    char *body = cJSON_PrintUnformatted(j);
    cJSON_Delete(j);
    if (!body) return false;

    char url[280];
    build_url(url, sizeof(url), "/api/cameras/provision");

    s_resp_len    = 0;
    s_resp_buf[0] = '\0';

    esp_http_client_config_t hcfg = {
        .url           = url,
        .method        = HTTP_METHOD_POST,
        .timeout_ms    = BACKEND_PROVISION_TIMEOUT_MS,
        .event_handler = http_event_handler,
    };
    if (strncmp(url, "https", 5) == 0)
        hcfg.crt_bundle_attach = esp_crt_bundle_attach;

    esp_http_client_handle_t c = esp_http_client_init(&hcfg);
    if (!c) { free(body); return false; }

    esp_http_client_set_header(c, "Content-Type", "application/json");
    esp_http_client_set_post_field(c, body, (int)strlen(body));

    int64_t t0  = esp_timer_get_time() / 1000;
    ESP_LOGI(TAG, "[PROV] → %s  cam=%ld mac=%s ip=%s",
             url, (long)cfg->camera_id, mac_str, ip);

    esp_err_t err = esp_http_client_perform(c);
    int64_t   dur = esp_timer_get_time() / 1000 - t0;

    bool ok = false;
    if (err == ESP_OK) {
        int scode = esp_http_client_get_status_code(c);
        if (scode >= 200 && scode < 300) {
            ok = true;
            cJSON *rj = (s_resp_len > 0) ? cJSON_Parse(s_resp_buf) : NULL;
            if (rj) {
                cJSON *cid = cJSON_GetObjectItemCaseSensitive(rj, "camera_id");
                if (cJSON_IsNumber(cid) && cid->valueint > 0) {
                    s_assigned_id = cid->valueint;
                    if (lock()) { s_cfg.camera_id = (int32_t)s_assigned_id; unlock(); }
                }
                cJSON_Delete(rj);
            }
            ESP_LOGI(TAG, "[PROV] OK cam=%d status=%d %lldms",
                     s_assigned_id > 0 ? s_assigned_id : (int)cfg->camera_id,
                     scode, dur);
        } else {
            ESP_LOGW(TAG, "[PROV] REJECT status=%d %lldms", scode, dur);
        }
    } else {
        ESP_LOGW(TAG, "[PROV] FAIL %s %lldms — sẽ retry", esp_err_to_name(err), dur);
    }

    esp_http_client_cleanup(c);
    free(body);
    return ok;
}

/* ─── Sync task ──────────────────────────────────────────────────────────── */
static void backend_sync_task(void *pv)
{
    (void)pv;
    ESP_LOGI(TAG, "task start");

    /* Chờ notify đầu tiên từ main (sau stream ready) */
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

    while (g_system_running) {

        /* Handle force-reprovision request */
        if (lock()) {
            if (s_force_reprov) {
                s_force_reprov = false;
                s_synced       = false;
                s_assigned_id  = -1;
                state_set("pending");
                ESP_LOGI(TAG, "[PROV] force reprovision");
            }
            unlock();
        }

        if (s_synced) {
            /* Đã sync — ngủ đến khi có notify (heartbeat / force-reprov) */
            ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
            continue;
        }

        /* Snapshot config + token */
        app_config_t cfg;
        char         tok[128];
        if (!lock()) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
        cfg = s_cfg;
        snprintf(tok, sizeof(tok), "%s", s_token);
        unlock();

        if (!tok[0]) {
            /* Chưa có token → đợi MQTT provision xong, thử lại sau */
            ESP_LOGW(TAG, "[PROV] no token yet, waiting...");
            state_set("waiting_token");
            vTaskDelay(pdMS_TO_TICKS(BACKEND_SYNC_RETRY_MS));
            continue;
        }

        state_set("syncing");
        bool ok = do_provision(&cfg, tok);

        if (ok) {
            bool is_new = (cfg.backend_synced == 0);

            if (lock()) {
                s_cfg.backend_synced = 1;
                if (s_assigned_id > 0) s_cfg.camera_id = (int32_t)s_assigned_id;
                cfg = s_cfg;
                unlock();
            }

            if (app_config_save(&cfg) == ESP_OK) {
                s_synced    = true;
                g_camera_id = (int)cfg.camera_id;
                state_set("synced");
                if (task_manager_post_connect_services_started()) {
                    task_manager_set_device_state(DEVICE_STATE_READY);
                    task_manager_set_system_ready(true);
                }
                mqtt_app_notify_backend_synced((int)cfg.camera_id, is_new);
                ESP_LOGI(TAG, "[PROV] synced cam=%ld %s",
                         (long)cfg.camera_id, is_new ? "new" : "reconnect");
            } else {
                state_set("save_error");
                ESP_LOGE(TAG, "[PROV] NVS save fail — sẽ retry");
                vTaskDelay(pdMS_TO_TICKS(BACKEND_SYNC_RETRY_MS));
            }
            continue;
        }

        /* Thất bại → chờ rồi thử lại, không bao giờ bỏ cuộc */
        state_set("provision_error");
        vTaskDelay(pdMS_TO_TICKS(BACKEND_SYNC_RETRY_MS));
    }

    s_task = NULL;
    ESP_LOGI(TAG, "task end");
    vTaskDelete(NULL);
}

/* ─── Public API ─────────────────────────────────────────────────────────── */
void backend_sync_start(const app_config_t *cfg, const char *token)
{
    if (s_task) return;
    if (!s_mtx) s_mtx = xSemaphoreCreateMutex();

    if (lock()) {
        s_cfg         = *cfg;
        s_synced      = false;
        s_assigned_id = -1;
        if (token && token[0])
            snprintf(s_token, sizeof(s_token), "%s", token);
        else
            s_token[0] = '\0';
        unlock();
    }

    s_force_reprov = false;
    state_set("pending");

    xTaskCreate(backend_sync_task, "backend_sync", 8192, NULL, 5, &s_task);
    ESP_LOGI(TAG, "start");
}

void backend_sync_set_token(const char *token)
{
    if (!token || !token[0]) return;
    if (lock()) { snprintf(s_token, sizeof(s_token), "%s", token); unlock(); }
}

void backend_sync_update_config(const app_config_t *cfg)
{
    if (!cfg) return;
    if (lock()) {
        app_config_t m = *cfg;
        if (s_assigned_id > 0)      m.camera_id      = (int32_t)s_assigned_id;
        else if (s_cfg.camera_id > 0) m.camera_id    = s_cfg.camera_id;
        if (s_cfg.backend_synced)   m.backend_synced = s_cfg.backend_synced;
        s_cfg = m;
        unlock();
    }
}

void backend_sync_notify(void)
{
    if (s_task) xTaskNotifyGive(s_task);
}

void backend_sync_force_reprovision(void)
{
    if (lock()) { s_force_reprov = true; unlock(); }
    backend_sync_notify();
}

void backend_sync_push_health(const health_telemetry_t *health)
{
    (void)health;
    /* Re-check backend health nếu cần (ví dụ: sau mất kết nối > N giây) */
    if (s_synced) backend_sync_notify();
}

void backend_sync_stop(void)
{
    g_system_running = false;
    backend_sync_notify();
}

bool        backend_sync_is_degraded(void)          { return false; /* không còn dùng */ }
const char *backend_sync_get_state_str(void)         { return s_state; }
int         backend_sync_get_assigned_camera_id(void){ return s_assigned_id; }
