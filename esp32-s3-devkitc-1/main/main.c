/*
 * main.c - Entry point for ESP32-S3-CAM firmware.
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <string.h>

#include "esp_app_desc.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_random.h"
#include "esp_system.h"
#include "nvs_flash.h"

#include "app_config.h"
#include "backend_sync.h"
#include "mqtt_app.h"
#include "stream_server.h"
#include "task_manager.h"
#include "tb_provisioning.h"
#include "wifi_manager.h"

static const char *TAG = "main";

#ifndef STARTUP_MQTT_READY_TIMEOUT_MS
#define STARTUP_MQTT_READY_TIMEOUT_MS 30000
#endif
#ifndef STARTUP_CAMERA_READY_TIMEOUT_MS
#define STARTUP_CAMERA_READY_TIMEOUT_MS 15000
#endif
#ifndef STARTUP_BACKEND_READY_TIMEOUT_MS
#define STARTUP_BACKEND_READY_TIMEOUT_MS 30000
#endif
#ifndef DEFAULT_TB_PROVISIONING_KEY
#error "DEFAULT_TB_PROVISIONING_KEY chua duoc dinh nghia."
#endif
#ifndef DEFAULT_TB_PROVISIONING_SECRET
#error "DEFAULT_TB_PROVISIONING_SECRET chua duoc dinh nghia."
#endif
#ifndef WIFI_MAX_RETRY
#error "WIFI_MAX_RETRY chua duoc dinh nghia."
#endif

static void configure_log_levels(void)
{
    static const char *quiet[] = {
        "boot", "esp_image", "esp_psram", "heap_init",
        "pp", "net80211", "wifi", "wifi_init",
        "esp_netif_handlers", "phy_init", "mqtt_client",
        "esp-tls", "transport_base", "HTTP_CLIENT",
        "cam_hal", "sccb-ng", "ov3660", "s3 ll_cam",
    };
    for (size_t i = 0; i < sizeof(quiet) / sizeof(quiet[0]); i++)
        esp_log_level_set(quiet[i], ESP_LOG_WARN);
    esp_log_level_set("httpd_txrx", ESP_LOG_ERROR);
    esp_log_level_set("httpd_uri",  ESP_LOG_ERROR);
}

static void log_net_identity(void)
{
    uint8_t mac[6] = {0};
    char ip[20]    = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    bool has_ip = wifi_get_ip_string(ip, sizeof(ip));
    ESP_LOGI(TAG, "NET mac=%02X:%02X:%02X:%02X:%02X:%02X ip=%s stream=http://%s:81/stream",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
             has_ip ? ip : "-", has_ip ? ip : "-");
}

static bool apply_default_boot_config(app_config_t *cfg)
{
    bool changed = false;
    if (DEFAULT_TB_PROVISIONING_KEY[0] && cfg->provisioning_key[0] == '\0') {
        strncpy(cfg->provisioning_key, DEFAULT_TB_PROVISIONING_KEY, sizeof(cfg->provisioning_key) - 1);
        changed = true;
    }
    if (DEFAULT_TB_PROVISIONING_SECRET[0] && cfg->provisioning_secret[0] == '\0') {
        strncpy(cfg->provisioning_secret, DEFAULT_TB_PROVISIONING_SECRET, sizeof(cfg->provisioning_secret) - 1);
        changed = true;
    }
    return changed;
}

static void ensure_random_device_name(app_config_t *cfg)
{
    if (!cfg) return;
    const char *pool = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    char suffix[7];
    for (int i = 0; i < 6; i++) suffix[i] = pool[esp_random() % strlen(pool)];
    suffix[6] = '\0';
    snprintf(cfg->device_name, sizeof(cfg->device_name), "Cam-%s", suffix);
    cfg->token[0]       = '\0';
    cfg->backend_synced = 0;
    if (app_config_save(cfg) != ESP_OK)
        ESP_LOGW(TAG, "cfg: save failed, using RAM identity");
    else
        ESP_LOGI(TAG, "cfg: new identity=%s", cfg->device_name);
}

static void apply_runtime_config(app_config_t *cfg)
{
    if (!cfg) return;
    g_camera_id = cfg->camera_id;
    ESP_LOGI(TAG, "cfg: dev=%s ssid=%s token=%s",
             cfg->device_name[0] ? cfg->device_name : "-",
             cfg->ssid[0]        ? cfg->ssid        : "-",
             cfg->token[0]       ? "yes"            : "no");
}

static bool wait_mqtt(void)
{
    TickType_t t0 = xTaskGetTickCount(), last_log = 0;
    while (!mqtt_app_is_connected()) {
        TickType_t now = xTaskGetTickCount();
        if ((now - t0) >= pdMS_TO_TICKS(STARTUP_MQTT_READY_TIMEOUT_MS)) {
            ESP_LOGE(TAG, "mqtt: timeout");
            return false;
        }
        if (last_log == 0 || (now - last_log) >= pdMS_TO_TICKS(5000)) {
            ESP_LOGI(TAG, "mqtt: connecting...");
            last_log = now;
        }
        vTaskDelay(pdMS_TO_TICKS(250));
    }
    return true;
}

static bool wait_camera(void)
{
    TickType_t t0 = xTaskGetTickCount(), last_log = 0;
    while (!g_camera_ok || g_frame_count == 0) {
        TickType_t now = xTaskGetTickCount();
        if ((now - t0) >= pdMS_TO_TICKS(STARTUP_CAMERA_READY_TIMEOUT_MS)) {
            ESP_LOGE(TAG, "cam: timeout ok=%d frames=%lu", g_camera_ok, (unsigned long)g_frame_count);
            return false;
        }
        if (last_log == 0 || (now - last_log) >= pdMS_TO_TICKS(3000)) {
            ESP_LOGI(TAG, "cam: waiting ok=%d frames=%lu", g_camera_ok, (unsigned long)g_frame_count);
            last_log = now;
        }
        vTaskDelay(pdMS_TO_TICKS(250));
    }
    return true;
}

void app_main(void)
{
    configure_log_levels();
    task_manager_set_system_ready(false);
    task_manager_set_device_state(DEVICE_STATE_BOOTING);

    const esp_app_desc_t *app = esp_app_get_description();
    ESP_LOGI(TAG, "=== %s v%s ===", app ? app->project_name : "fw", app ? app->version : "?");

    /* NVS */
    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES || nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "nvs: erase & reinit");
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_err);

    /* Config */
    app_config_t cfg;
    app_config_state_t cfg_state;
    ESP_ERROR_CHECK(app_config_load(&cfg, &cfg_state));
    if (cfg_state == APP_CONFIG_STATE_EMPTY) {
        app_config_set_defaults(&cfg);
        ensure_random_device_name(&cfg);
    } else if (cfg.device_name[0] == '\0') {
        ESP_LOGW(TAG, "cfg: missing device_name in NVS");
    }
    if (apply_default_boot_config(&cfg)) {
        if (app_config_save(&cfg) != ESP_OK)
            ESP_LOGW(TAG, "cfg: prov save failed");
    }
    apply_runtime_config(&cfg);
    task_manager_set_device_state(DEVICE_STATE_NET_CONNECTING);

    /* WiFi */
    wifi_manager_init();
    if (!wifi_manager_ensure_connected(&cfg, WIFI_MAX_RETRY)) {
        ESP_LOGE(TAG, "wifi: failed → reboot");
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }
    if (!wifi_manager_verify_connected_sta()) {
        ESP_LOGE(TAG, "wifi: verify failed → reboot");
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }
    task_manager_set_device_state(DEVICE_STATE_NET_READY);
    log_net_identity();

    /* Task manager */
    esp_err_t tm_err = task_manager_init(cfg.token[0] ? cfg.token : NULL);
    if (tm_err != ESP_OK) {
        ESP_LOGE(TAG, "task_mgr: init failed %s → reboot", esp_err_to_name(tm_err));
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }

    /* Camera */
    if (!wait_camera()) {
        ESP_LOGE(TAG, "cam: selftest fail → reboot");
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(2000));
        esp_restart();
    }
    ESP_LOGI(TAG, "cam: ok frames=%lu", (unsigned long)g_frame_count);

    /* MQTT */
    task_manager_set_device_state(DEVICE_STATE_MQTT_CONNECTING);
    if (!wait_mqtt()) {
        ESP_LOGE(TAG, "mqtt: selftest fail → reboot");
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(2000));
        esp_restart();
    }
    ESP_LOGI(TAG, "mqtt: connected");

    /* Stream */
    task_manager_set_device_state(DEVICE_STATE_STREAM_STARTING);
    if (stream_server_start() != ESP_OK) {
        ESP_LOGE(TAG, "stream: fail → reboot");
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(2000));
        esp_restart();
    }
    task_manager_set_device_state(DEVICE_STATE_STREAM_READY);
    backend_sync_notify();

    /* Sync camera_id từ backend */
    int assigned_id = backend_sync_get_assigned_camera_id();
    if (assigned_id > 0 && assigned_id != (int)cfg.camera_id) {
        cfg.camera_id = (int32_t)assigned_id;
        app_config_save(&cfg);
        apply_runtime_config(&cfg);
        ESP_LOGI(TAG, "cfg: camera_id=%d (from backend)", assigned_id);
    }

    /* Post-connect services */
    esp_err_t pc_err = task_manager_start_post_connect_services();
    if (pc_err != ESP_OK) {
        ESP_LOGE(TAG, "post-connect: %s → reboot", esp_err_to_name(pc_err));
        task_manager_set_device_state(DEVICE_STATE_FAULT);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }

    /* OTA partition verify */
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t ota_state;
    if (esp_ota_get_state_partition(running, &ota_state) == ESP_OK &&
        ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();
    }

    task_manager_set_device_state(DEVICE_STATE_READY);
    task_manager_set_system_ready(true);
    ESP_LOGI(TAG, "ready ✓");
}
