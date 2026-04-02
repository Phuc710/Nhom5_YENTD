/*
 * backend_sync.c — Backend HTTP sync task (provision + heartbeat).
 *
 * Tách biệt hoàn toàn khỏi mqtt_app.c:
 *   - MQTT control-plane (TB telemetry, RPC, attributes) → mqtt_app.c
 *   - HTTP data-plane (register + heartbeat backend) → đây
 *
 * Circuit breaker:
 *   - Provision fail >= BACKEND_SYNC_MAX_ATTEMPTS → degrade_mode = true
 *   - Degrade mode: retry interval BACKEND_SYNC_DEGRADE_INTERVAL_MS (60s)
 *   - Heartbeat 404 → reset về provision phase (backend mất mapping)
 *   - Bất kỳ 2xx nào → reset circuit, back to normal
 *
 * sync_inflight flag:
 *   - Chỉ 1 HTTP request chạy tại 1 thời điểm
 *   - Notify trong lúc inflight sẽ được consume sau khi request xong
 */
#include "backend_sync.h"
#include "app_config.h"
#include "task_manager.h"
#include "wifi_manager.h"

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_ota_ops.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include <string.h>
#include <stdlib.h>

static const char *TAG = "backend_sync";

#ifndef BACKEND_SYNC_MAX_ATTEMPTS
#define BACKEND_SYNC_MAX_ATTEMPTS 3
#endif

/* ---- State nội bộ (thread-safe qua mutex và atomic flag) ---- */
static TaskHandle_t      s_task_handle        = NULL;
static SemaphoreHandle_t s_cfg_mutex          = NULL;
static SemaphoreHandle_t s_health_mutex       = NULL;

static app_config_t      s_cfg;                     /* Protected bởi s_cfg_mutex */
static char              s_token[128]         = {0}; /* Protected bởi s_cfg_mutex */

static health_telemetry_t s_health_snap;             /* Protected bởi s_health_mutex */
static bool               s_health_ready      = false;

/* Các flag/counter chạy trong task → không cần mutex */
static bool     s_backend_synced      = false;  /* true khi provision 2xx */
static bool     s_force_reprovision   = false;  /* set từ ngoài, reset trong task */
static int      s_prov_fail_count     = 0;
static bool     s_degrade_mode        = false;
static char     s_state_str[48]       = "pending";

/* sync_inflight: volatile bool dùng task context only (không cần mutex) */
static volatile bool s_inflight       = false;
static volatile bool s_pending_notify = false;

/* ---------- Internal helpers ---------- */

static void state_set(const char *s)
{
    snprintf(s_state_str, sizeof(s_state_str), "%s", s ? s : "unknown");
}

static bool cfg_lock(void)
{
    return s_cfg_mutex &&
           xSemaphoreTake(s_cfg_mutex, pdMS_TO_TICKS(30)) == pdTRUE;
}

static void cfg_unlock(void)
{
    xSemaphoreGive(s_cfg_mutex);
}

static bool health_lock(void)
{
    return s_health_mutex &&
           xSemaphoreTake(s_health_mutex, pdMS_TO_TICKS(20)) == pdTRUE;
}

static void health_unlock(void)
{
    xSemaphoreGive(s_health_mutex);
}

/* ---------- HTTP helpers ---------- */

static void compact_text(char *text)
{
    if (!text) return;
    for (char *p = text; *p; ++p) {
        if (*p == '\r' || *p == '\n' || *p == '\t') *p = ' ';
    }
}

static void read_resp_preview(esp_http_client_handle_t client,
                              char *out, size_t out_len)
{
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!client) return;
    int content_len = esp_http_client_get_content_length(client);
    if (content_len == 0) { snprintf(out, out_len, "<empty>"); return; }
    int n = esp_http_client_read(client, out, (int)(out_len - 1));
    if (n <= 0) { snprintf(out, out_len, "<no-body>"); return; }
    out[n] = '\0';
    compact_text(out);
}

static void build_backend_url(char *out, size_t out_len, const char *path)
{
    if (!out || out_len == 0 || !path) return;
    size_t base_len = strlen(BACKEND_UPLOAD_URL);
    bool base_slash = (base_len > 0 && BACKEND_UPLOAD_URL[base_len - 1] == '/');
    bool path_slash = (path[0] == '/');
    if (base_slash && path_slash)
        snprintf(out, out_len, "%s%s", BACKEND_UPLOAD_URL, path + 1);
    else if (!base_slash && !path_slash)
        snprintf(out, out_len, "%s/%s", BACKEND_UPLOAD_URL, path);
    else
        snprintf(out, out_len, "%s%s", BACKEND_UPLOAD_URL, path);
}

/* ---------- Device identity snapshot (caches mac, ip, names) ---------- */

typedef struct {
    uint8_t mac[6];
    char    mac_str[18];
    char    ip[20];
    char    stream_url[64];
    char    tb_device_name[48];
    char    device_name[64];
    char    resolution[24];
    bool    has_ip;
} dev_snap_t;

static void snap_device(dev_snap_t *s, const app_config_t *cfg)
{
    esp_read_mac(s->mac, ESP_MAC_WIFI_STA);
    snprintf(s->mac_str, sizeof(s->mac_str),
             "%02X:%02X:%02X:%02X:%02X:%02X",
             s->mac[0], s->mac[1], s->mac[2], s->mac[3], s->mac[4], s->mac[5]);

    s->has_ip = wifi_get_ip_string(s->ip, sizeof(s->ip));

    if (s->has_ip)
        snprintf(s->stream_url, sizeof(s->stream_url), "http://%s:81/stream", s->ip);
    else
        s->stream_url[0] = '\0';

    if (cfg->device_name[0])
        snprintf(s->tb_device_name, sizeof(s->tb_device_name), "%s", cfg->device_name);
    else
        snprintf(s->tb_device_name, sizeof(s->tb_device_name),
                 "cam-%02X%02X%02X%02X%02X%02X",
                 s->mac[0], s->mac[1], s->mac[2], s->mac[3], s->mac[4], s->mac[5]);

    snprintf(s->device_name, sizeof(s->device_name),
             "%s", cfg->device_name[0] ? cfg->device_name : s->tb_device_name);

    snprintf(s->resolution, sizeof(s->resolution), "VGA"); /* fallback */
}

/* ---------- Provision HTTP call ---------- */

static bool do_provision(const app_config_t *cfg, const char *token)
{
    if (!token || !token[0]) {
        ESP_LOGW(TAG, "[PROV] Bỏ qua — chưa có token");
        return false;
    }

    dev_snap_t d;
    snap_device(&d, cfg);
    if (!d.has_ip) {
        ESP_LOGW(TAG, "[PROV] Bỏ qua — chưa có IP");
        return false;
    }

    const esp_app_desc_t *app = esp_app_get_description();
    const char *project = (app && app->project_name[0]) ? app->project_name : BACKEND_SYNC_DEVICE_PREFIX;

    cJSON *root = cJSON_CreateObject();
    if (!root) return false;

    cJSON_AddNumberToObject(root, "camera_id",           cfg->camera_id);
    cJSON_AddStringToObject(root, "camera_name",         d.device_name);
    cJSON_AddStringToObject(root, "tb_device_name",      d.tb_device_name);
    cJSON_AddStringToObject(root, "mac_address",         d.mac_str);
    cJSON_AddStringToObject(root, "ip_address",          d.ip);
    cJSON_AddStringToObject(root, "stream_url",          d.stream_url);
    cJSON_AddStringToObject(root, "location",            cfg->location);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return false;

    char url[280];
    build_backend_url(url, sizeof(url), "/api/cameras/provision");

    esp_http_client_config_t hcfg = {
        .url        = url,
        .method     = HTTP_METHOD_POST,
        .timeout_ms = BACKEND_PROVISION_TIMEOUT_MS,
    };
    if (strncmp(url, "https", 5) == 0) hcfg.crt_bundle_attach = esp_crt_bundle_attach;

    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    if (!client) { free(body); return false; }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, strlen(body));

    int64_t t0 = esp_timer_get_time() / 1000;
    ESP_LOGI(TAG, "🚀 [PROV] cam=%ld mac=%s ip=%s url=%s",
             (long)cfg->camera_id, d.mac_str, d.ip, url);

    esp_err_t err = esp_http_client_perform(client);
    int64_t   dur = (esp_timer_get_time() / 1000) - t0;

    bool ok = false;
    if (err == ESP_OK) {
        int scode = esp_http_client_get_status_code(client);
        char resp[256];
        read_resp_preview(client, resp, sizeof(resp));
        if (scode >= 200 && scode < 300) {
            ESP_LOGI(TAG, "✅ [PROV] OK cam=%ld status=%d %lldms resp=%s",
                     (long)cfg->camera_id, scode, dur, resp);
            ok = true;
        } else {
            ESP_LOGW(TAG, "❌ [PROV] REJECT cam=%ld status=%d %lldms resp=%s",
                     (long)cfg->camera_id, scode, dur, resp);
        }
    } else {
        ESP_LOGE(TAG, "⚠️ [PROV] FAIL cam=%ld err=%s timeout=%dms actual=%lldms url=%s",
                 (long)cfg->camera_id, esp_err_to_name(err),
                 BACKEND_PROVISION_TIMEOUT_MS, dur, url);
    }

    esp_http_client_cleanup(client);
    free(body);
    return ok;
}

/* ---------- Heartbeat HTTP call ---------- */

static bool do_heartbeat(const app_config_t *cfg,
                         const health_telemetry_t *health,
                         int *out_status)
{
    if (out_status) *out_status = 0;
    if (!health) return false;

    dev_snap_t d;
    snap_device(&d, cfg);
    if (!d.has_ip) {
        ESP_LOGW(TAG, "[HB] Bỏ qua — chưa có IP");
        return false;
    }

    const char *light_mode =
        (health->light_state == 0) ? "RED" :
        (health->light_state == 1) ? "YELLOW" : "GREEN";

    cJSON *root = cJSON_CreateObject();
    if (!root) return false;

    cJSON_AddNumberToObject(root, "camera_id",           cfg->camera_id);
    cJSON_AddStringToObject(root, "mac_address",         d.mac_str);
    cJSON_AddStringToObject(root, "ip_address",          d.ip);
    cJSON_AddStringToObject(root, "stream_url",          d.stream_url);
    cJSON_AddBoolToObject  (root, "online",              true);
    cJSON_AddStringToObject(root, "device_state",
        health->device_state[0] ? health->device_state : "running");
    cJSON_AddStringToObject(root, "light_state",         light_mode);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return false;

    char url[280];
    build_backend_url(url, sizeof(url), "/api/cameras/heartbeat");

    esp_http_client_config_t hcfg = {
        .url        = url,
        .method     = HTTP_METHOD_POST,
        .timeout_ms = BACKEND_HEARTBEAT_TIMEOUT_MS,
    };
    if (strncmp(url, "https", 5) == 0) hcfg.crt_bundle_attach = esp_crt_bundle_attach;

    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    if (!client) { free(body); return false; }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, strlen(body));

    int64_t t0 = esp_timer_get_time() / 1000;
    ESP_LOGI(TAG, "🚀 [HB] cam=%ld light=%s heap=%lu rssi=%d",
             (long)cfg->camera_id, light_mode,
             (unsigned long)health->free_heap, (int)health->wifi_rssi);

    esp_err_t err = esp_http_client_perform(client);
    int64_t   dur = (esp_timer_get_time() / 1000) - t0;

    int scode = esp_http_client_get_status_code(client);
    if (out_status) *out_status = scode;

    bool ok = (err == ESP_OK && scode >= 200 && scode < 300);
    char resp[256];
    read_resp_preview(client, resp, sizeof(resp));

    if (ok) {
        ESP_LOGI(TAG, "✅ [HB] OK cam=%ld status=%d %lldms",
                 (long)cfg->camera_id, scode, dur);
    } else if (err == ESP_OK) {
        ESP_LOGW(TAG, "❌ [HB] REJECT cam=%ld status=%d %lldms resp=%s",
                 (long)cfg->camera_id, scode, dur, resp);
    } else {
        ESP_LOGE(TAG, "⚠️ [HB] FAIL cam=%ld err=%s timeout=%dms actual=%lldms",
                 (long)cfg->camera_id, esp_err_to_name(err),
                 BACKEND_HEARTBEAT_TIMEOUT_MS, dur);
    }

    esp_http_client_cleanup(client);
    free(body);
    return ok;
}

/* ---------- Background task ---------- */

static void backend_sync_task(void *pv)
{
    (void)pv;
    ESP_LOGI(TAG, "Task backend_sync khởi động");

    TickType_t last_prov_tick  = 0;
    TickType_t last_hb_tick    = 0;

    while (g_system_running) {

        /* Đợi notify hoặc timeout ngắn để poll flag */
        uint32_t wait_ms = 1000;
        if (!s_backend_synced) {
            uint32_t retry_ms = s_degrade_mode
                                ? BACKEND_SYNC_DEGRADE_INTERVAL_MS
                                : BACKEND_SYNC_RETRY_MS;
            TickType_t now = xTaskGetTickCount();
            TickType_t elapsed = now - last_prov_tick;
            if (last_prov_tick != 0 && elapsed < pdMS_TO_TICKS(retry_ms)) {
                wait_ms = pdTICKS_TO_MS(pdMS_TO_TICKS(retry_ms) - elapsed);
                if (wait_ms > retry_ms) wait_ms = retry_ms;
            } else {
                wait_ms = 200;
            }
        } else {
            TickType_t now = xTaskGetTickCount();
            TickType_t elapsed = now - last_hb_tick;
            if (last_hb_tick != 0 && elapsed < pdMS_TO_TICKS(BACKEND_HEARTBEAT_INTERVAL_MS)) {
                wait_ms = pdTICKS_TO_MS(pdMS_TO_TICKS(BACKEND_HEARTBEAT_INTERVAL_MS) - elapsed);
                if (wait_ms > BACKEND_HEARTBEAT_INTERVAL_MS)
                    wait_ms = BACKEND_HEARTBEAT_INTERVAL_MS;
            } else {
                wait_ms = 200;
            }
        }

        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(wait_ms));
        s_pending_notify = false;

        /* ----- Lấy snapshot config thread-safe ----- */
        app_config_t  local_cfg;
        char          local_token[128];
        if (!cfg_lock()) continue;
        local_cfg = s_cfg;
        snprintf(local_token, sizeof(local_token), "%s", s_token);
        bool force_reprov = s_force_reprovision;
        s_force_reprovision = false;
        cfg_unlock();

        if (force_reprov) {
            s_backend_synced   = false;
            last_prov_tick     = 0;
            last_hb_tick       = 0;
            s_prov_fail_count  = 0;
            s_degrade_mode     = false;
            state_set("pending_reprovision");
        }

        /* ----- Phase A: Provision ----- */
        if (!s_backend_synced) {
            TickType_t now     = xTaskGetTickCount();
            uint32_t retry_ms = s_degrade_mode
                                ? BACKEND_SYNC_DEGRADE_INTERVAL_MS
                                : BACKEND_SYNC_RETRY_MS;

            /* Chưa đến thời điểm retry — bỏ qua */
            if (last_prov_tick != 0 &&
                (now - last_prov_tick) < pdMS_TO_TICKS(retry_ms)) {
                continue;
            }

            last_prov_tick = now;
            s_inflight     = true;

            bool ok = do_provision(&local_cfg, local_token);

            s_inflight = false;

            if (ok) {
                s_backend_synced  = true;
                s_prov_fail_count = 0;
                s_degrade_mode    = false;
                last_hb_tick      = 0; /* force ngay heartbeat đầu tiên */
                state_set("synced");
                ESP_LOGI(TAG, "✅ [PROV] Đồng bộ backend thành công");

                /* Lưu backend_synced vào NVS */
                if (cfg_lock()) {
                    s_cfg.backend_synced = 1;
                    app_config_t save_cfg = s_cfg;
                    cfg_unlock();
                    app_config_save(&save_cfg);
                }
            } else {
                s_prov_fail_count++;
                if (s_prov_fail_count >= BACKEND_SYNC_MAX_ATTEMPTS && !s_degrade_mode) {
                    s_degrade_mode = true;
                    ESP_LOGW(TAG,
                             "⚠️ [CIRCUIT] Provision fail %d lần liên tiếp → degrade mode "
                             "(retry mỗi %ds)",
                             s_prov_fail_count,
                             BACKEND_SYNC_DEGRADE_INTERVAL_MS / 1000);
                }
                state_set(s_degrade_mode ? "degraded" : "provision_error");
            }
            continue;
        }

        /* Lấy health snapshot chỉ để log nếu cần hoặc phục vụ provision */
        health_telemetry_t health = {0};
        if (health_lock()) {
            if (s_health_ready) health = s_health_snap;
            health_unlock();
        }

        /* 
         * [MQTT-FIRST] Bỏ qua nhịp tim định kỳ qua HTTP. 
         * Tất cả trạng thái Đèn + Sức khỏe đã chuyển sang MQTT (ThingsBoard).
         * Chỉ duy trì task để đợi Notify nếu cần Re-provision khi đổi IP/NVS.
         */
        wait_ms = portMAX_DELAY; 
        continue;

    }

    s_task_handle = NULL;
    ESP_LOGI(TAG, "Task backend_sync kết thúc");
    vTaskDelete(NULL);
}

/* ---------- Public API ---------- */

void backend_sync_start(const app_config_t *cfg, const char *token)
{
    if (s_task_handle) return; /* Already running */

    if (!s_cfg_mutex)    s_cfg_mutex    = xSemaphoreCreateMutex();
    if (!s_health_mutex) s_health_mutex = xSemaphoreCreateMutex();

    if (cfg_lock()) {
        s_cfg = *cfg;
        s_backend_synced = (cfg->backend_synced == 1);
        if (token && token[0]) {
            snprintf(s_token, sizeof(s_token), "%s", token);
        }
        cfg_unlock();
    }

    state_set(s_backend_synced ? "synced" : "pending");

    xTaskCreate(backend_sync_task, "backend_sync",
                8192, NULL, 5, &s_task_handle);
    ESP_LOGI(TAG, "backend_sync_start → task created (synced=%d)", s_backend_synced);
}

void backend_sync_set_token(const char *token)
{
    if (!token || !token[0]) return;
    if (cfg_lock()) {
        snprintf(s_token, sizeof(s_token), "%s", token);
        cfg_unlock();
    }
}

void backend_sync_update_config(const app_config_t *cfg)
{
    if (!cfg) return;
    if (cfg_lock()) {
        s_cfg = *cfg;
        cfg_unlock();
    }
}

void backend_sync_notify(void)
{
    if (s_inflight) {
        /* Request đang bay — đánh dấu pending, task sẽ tự xử lý sau khi xong */
        s_pending_notify = true;
        return;
    }
    if (s_task_handle) {
        xTaskNotifyGive(s_task_handle);
    }
}

void backend_sync_force_reprovision(void)
{
    if (cfg_lock()) {
        s_force_reprovision = true;
        cfg_unlock();
    }
    backend_sync_notify();
}

void backend_sync_push_health(const health_telemetry_t *health)
{
    if (!health) return;
    if (health_lock()) {
        s_health_snap  = *health;
        s_health_ready = true;
        health_unlock();
    }
    /* Notify nếu cần heartbeat và không inflight */
    if (!s_inflight && s_backend_synced) {
        backend_sync_notify();
    }
}

void backend_sync_stop(void)
{
    g_system_running = false;
    backend_sync_notify(); /* wake task để thoát loop */
}

bool backend_sync_is_degraded(void)
{
    return s_degrade_mode;
}

const char *backend_sync_get_state_str(void)
{
    return s_state_str;
}
