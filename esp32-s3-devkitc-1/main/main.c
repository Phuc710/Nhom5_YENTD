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
#include "led_status.h"
#include "stream_server.h"
#include "task_manager.h"
#include "tb_provisioning.h"
#include "wifi_manager.h"

static const char *TAG = "main";

#ifndef DEFAULT_TB_PROVISIONING_KEY
#error "DEFAULT_TB_PROVISIONING_KEY chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef DEFAULT_TB_PROVISIONING_SECRET
#error "DEFAULT_TB_PROVISIONING_SECRET chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_MAX_RETRY
#error "WIFI_MAX_RETRY chua duoc dinh nghia. Dat trong platformio.ini."
#endif

static void configure_system_log_levels(void)
{
    static const char *quiet_tags[] = {
        "boot",
        "esp_image",
        "esp_psram",
        "heap_init",
        "pp",
        "net80211",
        "wifi",
        "wifi_init",
        "esp_netif_handlers",
        "phy_init",
        "mqtt_client",
        "esp-tls",
        "transport_base",
        "HTTP_CLIENT",
        "cam_hal",
        "camera",
        "sccb-ng",
        "ov5640",
        "ov3660",
        "s3 ll_cam",
    };

    for (size_t i = 0; i < sizeof(quiet_tags) / sizeof(quiet_tags[0]); ++i) {
        esp_log_level_set(quiet_tags[i], ESP_LOG_WARN);
    }

    // Browser dong stream giua chung la tinh huong binh thuong, khong can spam warning.
    esp_log_level_set("httpd_txrx", ESP_LOG_ERROR);
    esp_log_level_set("httpd_uri", ESP_LOG_ERROR);
}

static void log_network_identity(void)
{
    uint8_t mac[6] = {0};
    char ip[20] = {0};
    char stream_url[64] = {0};
    bool has_mac = esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK;
    bool has_ip = wifi_get_ip_string(ip, sizeof(ip));

    if (has_ip) {
        snprintf(stream_url, sizeof(stream_url), "http://%s:81/stream", ip);
    }

    if (has_mac) {
        ESP_LOGI(
            TAG,
            "NET | MAC=%02X:%02X:%02X:%02X:%02X:%02X IP=%s STREAM=%s",
            mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
            has_ip ? ip : "-",
            has_ip ? stream_url : "-"
        );
    }
}

static void apply_default_boot_config(app_config_t *cfg)
{
    if (!cfg) {
        return;
    }

    if (DEFAULT_TB_PROVISIONING_KEY[0] && cfg->provisioning_key[0] == '\0') {
        strncpy(cfg->provisioning_key, DEFAULT_TB_PROVISIONING_KEY, sizeof(cfg->provisioning_key) - 1);
    }
    if (DEFAULT_TB_PROVISIONING_SECRET[0] && cfg->provisioning_secret[0] == '\0') {
        strncpy(
            cfg->provisioning_secret,
            DEFAULT_TB_PROVISIONING_SECRET,
            sizeof(cfg->provisioning_secret) - 1
        );
    }
}

static void ensure_random_device_name(app_config_t *cfg)
{
    if (!cfg) {
        return;
    }

    const char *pool = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    char previous_name[sizeof(cfg->device_name)] = {0};
    char suffix[7];

    if (cfg->device_name[0]) {
        snprintf(previous_name, sizeof(previous_name), "%s", cfg->device_name);
    }

    for (int i = 0; i < 6; i++) {
        suffix[i] = pool[esp_random() % strlen(pool)];
    }
    suffix[6] = '\0';

    snprintf(cfg->device_name, sizeof(cfg->device_name), "Cam-%s", suffix);
    cfg->token[0] = '\0';
    cfg->backend_synced = 0;

    if (app_config_save(cfg) != ESP_OK) {
        ESP_LOGW(TAG, "CFG | không lưu được identity random mới, tiếp tục chạy bằng RAM");
        return;
    }

    ESP_LOGI(
        TAG,
        "CFG | random device identity | prev=%s next=%s reprovision=yes",
        previous_name[0] ? previous_name : "(trống)",
        cfg->device_name
    );
}

static void apply_runtime_config(app_config_t *cfg)
{
    if (!cfg) {
        return;
    }

    g_camera_id = cfg->camera_id;
    ESP_LOGI(TAG, "CFG | device=%s camera_id=%d ssid=%s token=%s prov=%s",
             cfg->device_name[0] ? cfg->device_name : "-",
             g_camera_id,
             cfg->ssid[0] ? cfg->ssid : "-",
             cfg->token[0] ? "yes" : "no",
             tb_has_prov_credentials(cfg) ? "yes" : "no");
}

void app_main(void)
{
    configure_system_log_levels();
    ESP_LOGI(TAG, "BOOT | start");

    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES ||
        nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS | reset");
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_err);

    app_config_t cfg;
    app_config_state_t cfg_state;
    ESP_ERROR_CHECK(app_config_load(&cfg, &cfg_state));

    if (cfg_state == APP_CONFIG_STATE_EMPTY) {
        app_config_set_defaults(&cfg);
    }

    ensure_random_device_name(&cfg);
    apply_default_boot_config(&cfg);
    apply_runtime_config(&cfg);

    led_status_init();
    led_status_set_rgb(8, 8, 8);

    wifi_manager_init();
    if (!wifi_manager_ensure_connected(&cfg, WIFI_MAX_RETRY)) {
        ESP_LOGE(TAG, "WIFI | failed, reboot");
        led_status_set_rgb(48, 0, 0);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }
    if (!wifi_manager_verify_connected_sta()) {
        ESP_LOGE(TAG, "WIFI | link/ip verify failed, reboot");
        led_status_set_rgb(48, 24, 0);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }
    ESP_LOGI(TAG, "WIFI | ok");
    log_network_identity();

    if (!tb_has_token(&cfg)) {
        if (tb_has_prov_credentials(&cfg)) {
            led_status_set_rgb(0, 32, 32);
            if (tb_provision_device(&cfg)) {
                led_status_set_rgb(0, 48, 0);
                ESP_LOGI(TAG, "PROV | ok");
            } else {
                led_status_set_rgb(48, 24, 0);
                ESP_LOGW(TAG, "PROV | failed, retry later");
            }
        } else {
            ESP_LOGW(TAG, "PROV | skipped, no credentials");
        }
    } else {
        ESP_LOGI(TAG, "PROV | skipped, token exists");
    }

    led_status_set_rgb(0, 16, 32);
    esp_err_t tm_err = task_manager_init(cfg.token[0] ? cfg.token : NULL);
    if (tm_err != ESP_OK) {
        ESP_LOGE(TAG, "TASK | init failed: %s", esp_err_to_name(tm_err));
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }

    esp_err_t stream_err = stream_server_start();
    if (stream_err == ESP_OK) {
        ESP_LOGI(TAG, "STREAM | ok");
    } else {
        ESP_LOGW(TAG, "STREAM | fail");
    }

    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t ota_state;
    if (esp_ota_get_state_partition(running, &ota_state) == ESP_OK &&
        ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();
    }

    const esp_app_desc_t *app = esp_app_get_description();
    if (app) {
        ESP_LOGI(TAG, "APP | %s v%s", app->project_name, app->version);
    }

    led_status_white();
    ESP_LOGI(TAG, "BOOT | ready");
}
