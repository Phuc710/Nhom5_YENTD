/*
 * main.c - Diem vao chinh cua firmware ESP32-S3-CAM
 *
 * Boot sequence:
 *   1. NVS init
 *   2. Doc config (SSID, token, provisioning credentials)
 *   3. LED init
 *   4. WiFi manager: STA neu co WiFi, AP portal neu chua co/sai WiFi
 *   5. Provisioning neu chua co token
 *   6. Task manager init (camera, uploader, mqtt, health, button)
 *   7. Danh dau firmware hop le (OTA rollback protection)
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_mac.h"
#include <string.h>

#include "app_config.h"
#include "led_status.h"
#include "wifi_manager.h"
#include "tb_provisioning.h"
#include "task_manager.h"
#include "stream_server.h"

static const char *TAG = "main";

#ifndef DEFAULT_TB_PROVISIONING_KEY
#define DEFAULT_TB_PROVISIONING_KEY ""
#endif
#ifndef DEFAULT_TB_PROVISIONING_SECRET
#define DEFAULT_TB_PROVISIONING_SECRET ""
#endif

#define WIFI_MAX_RETRY 10

static void log_network_identity(void)
{
    uint8_t mac[6] = {0};
    char ip[20] = {0};
    char stream_url[64] = {0};
    bool has_mac = esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK;
    bool has_ip = wifi_get_ip_string(ip, sizeof(ip));

    if (has_ip) {
        snprintf(stream_url, sizeof(stream_url), "http://%s/stream", ip);
    }

    if (has_mac) {
        ESP_LOGI(
            TAG,
            "Nhận diện thiết bị: MAC=%02X:%02X:%02X:%02X:%02X:%02X | IP=%s | Stream=%s",
            mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
            has_ip ? ip : "(chưa có)",
            has_ip ? stream_url : "(chưa có)"
        );
    } else {
        ESP_LOGW(TAG, "Không đọc được MAC WiFi STA để log nhận diện thiết bị");
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

static void apply_default_runtime_state(const app_config_t *cfg)
{
    if (cfg &&
        cfg->frames_per_upload > 0 &&
        cfg->frames_per_upload <= APP_CONFIG_MAX_FRAMES_PER_UPLOAD) {
        g_frames_per_upload = cfg->frames_per_upload;
    }

    ESP_LOGI(
        TAG,
        "Mặc định runtime: camera_id=%d interval=%lums save_img=%s frames_per_upload=%u",
        g_camera_id,
        (unsigned long)g_capture_interval_ms,
        g_save_img ? "bật" : "tắt",
        (unsigned)g_frames_per_upload
    );
}

void app_main(void)
{
    ESP_LOGI(TAG, "======================================");
    ESP_LOGI(TAG, "  ESP32-S3-CAM bắt đầu khởi động firmware");
    ESP_LOGI(TAG, "======================================");

    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES ||
        nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_LOGW(TAG, "NVS bị lỗi, xóa và khởi tạo lại");
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_err);
    ESP_LOGI(TAG, "[1/7] NVS khởi tạo OK");

    app_config_t cfg;
    app_config_state_t cfg_state;
    ESP_ERROR_CHECK(app_config_load(&cfg, &cfg_state));

    if (cfg_state == APP_CONFIG_STATE_EMPTY) {
        ESP_LOGW(TAG, "Chưa có config, dùng giá trị mặc định");
        app_config_set_defaults(&cfg);
    }
    apply_default_boot_config(&cfg);
    apply_default_runtime_state(&cfg);

    ESP_LOGI(
        TAG,
        "[2/7] Config SSID=%s Token=%s Provisioning=%s",
        cfg.ssid[0] ? cfg.ssid : "(trống)",
        cfg.token[0] ? "(có)" : "(trống)",
        tb_has_prov_credentials(&cfg) ? "(có)" : "(trống)"
    );

    led_status_init();
    led_status_set_rgb(8, 8, 8);
    ESP_LOGI(TAG, "[3/7] LED RGB khởi tạo OK");

    wifi_manager_init();
    bool wifi_ok = wifi_manager_ensure_connected(&cfg, WIFI_MAX_RETRY);
    if (!wifi_ok) {
        ESP_LOGE(TAG, "WiFi manager gặp lỗi nghiêm trọng, khởi động lại sau 5s");
        led_status_set_rgb(48, 0, 0);
        vTaskDelay(pdMS_TO_TICKS(5000));
        esp_restart();
    }
    ESP_LOGI(TAG, "[4/7] WiFi đã kết nối");
    log_network_identity();

    if (!tb_has_token(&cfg)) {
        if (tb_has_prov_credentials(&cfg)) {
            ESP_LOGI(TAG, "[5/7] Chưa có token, thử provisioning...");
            led_status_set_rgb(0, 32, 32);
            bool prov_ok = tb_provision_device(&cfg);
            if (prov_ok) {
                led_status_set_rgb(0, 48, 0);
                ESP_LOGI(TAG, "[5/7] Provisioning thành công");
            } else {
                led_status_set_rgb(48, 24, 0);
                ESP_LOGW(TAG, "[5/7] Provisioning thất bại, sẽ thử lại trong MQTT task");
            }
        } else {
            ESP_LOGW(TAG, "[5/7] Không có provisioning credentials, bỏ qua");
        }
    } else {
        ESP_LOGI(TAG, "[5/7] Đã có token, bỏ qua provisioning");
    }

    led_status_set_rgb(0, 16, 32);
    esp_err_t tm_err = task_manager_init(cfg.token[0] ? cfg.token : NULL);
    if (tm_err != ESP_OK) {
        ESP_LOGE(TAG, "Task manager thất bại: %s, reboot sau 3s", esp_err_to_name(tm_err));
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }
    ESP_LOGI(TAG, "[6/7] Tất cả task đã khởi động");

    esp_err_t stream_err = stream_server_start();
    if (stream_err == ESP_OK) {
        ESP_LOGI(TAG, "[6.1/7] HTTP stream local đã bật: /stream và /snapshot");
    } else {
        ESP_LOGW(TAG, "[6.1/7] Không bật được HTTP stream local");
    }

    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t ota_state;
    if (esp_ota_get_state_partition(running, &ota_state) == ESP_OK &&
        ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();
        ESP_LOGI(TAG, "[7/7] Firmware đã xác nhận hợp lệ (OTA rollback protection)");
    } else {
        ESP_LOGI(TAG, "[7/7] Firmware bình thường (không phải OTA boot)");
    }

    const esp_app_desc_t *app = esp_app_get_description();
    if (app) {
        ESP_LOGI(TAG, "Firmware: %s v%s | Build: %s %s",
                 app->project_name, app->version, app->date, app->time);
    }

    led_status_white();
    ESP_LOGI(TAG, "======================================");
    ESP_LOGI(TAG, "  Khởi động hoàn tất!");
    ESP_LOGI(TAG, "======================================");
}
