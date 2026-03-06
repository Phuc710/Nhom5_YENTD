/*
 * main.c — Điểm vào chính của firmware ESP32-S3-CAM
 *
 * Boot sequence:
 *   1. NVS init
 *   2. Đọc config (SSID, token, prov credentials)
 *   3. LED init
 *   4. WiFi kết nối
 *   5. Provisioning nếu chưa có token
 *   6. Task manager init (camera, uploader, mqtt, health, button)
 *   7. Đánh dấu firmware hợp lệ (OTA rollback protection)
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_timer.h"

#include "app_config.h"
#include "led_status.h"
#include "wifi_manager.h"
#include "tb_provisioning.h"
#include "task_manager.h"

static const char *TAG = "main";

/* Cấu hình WiFi mặc định (override từ menuconfig / Kconfig) */
#ifndef DEFAULT_WIFI_SSID
#define DEFAULT_WIFI_SSID     ""
#endif
#ifndef DEFAULT_WIFI_PASS
#define DEFAULT_WIFI_PASS     ""
#endif

/* Số lần retry WiFi khi boot */
#define WIFI_MAX_RETRY 10

void app_main(void)
{
    ESP_LOGI(TAG, "======================================");
    ESP_LOGI(TAG, "  ESP32-S3-CAM Firmware boot");
    ESP_LOGI(TAG, "======================================");

    /* 1. Khởi tạo NVS */
    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES ||
        nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS bị lỗi, xóa và khởi tạo lại");
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_err);
    ESP_LOGI(TAG, "[1/7] NVS khởi tạo OK");

    /* 2. Đọc config từ NVS */
    app_config_t cfg;
    app_config_state_t cfg_state;
    ESP_ERROR_CHECK(app_config_load(&cfg, &cfg_state));

    if (cfg_state == APP_CONFIG_STATE_EMPTY) {
        ESP_LOGW(TAG, "Chưa có config — dùng giá trị mặc định");
        app_config_set_defaults(&cfg);
        /* Điền SSID/pass từ build flags nếu có */
        if (DEFAULT_WIFI_SSID[0]) {
            strncpy(cfg.ssid, DEFAULT_WIFI_SSID, sizeof(cfg.ssid)-1);
            strncpy(cfg.password, DEFAULT_WIFI_PASS, sizeof(cfg.password)-1);
        }
    }
    ESP_LOGI(TAG, "[2/7] Config SSID=%s Token=%s",
             cfg.ssid, cfg.token[0] ? "(có)" : "(trống)");

    /* 3. LED khởi tạo */
    led_status_init();
    led_status_set_rgb(8, 8, 8); /* Trắng mờ — đang boot */
    ESP_LOGI(TAG, "[3/7] LED RGB khởi tạo OK");

    /* 4. WiFi kết nối */
    wifi_manager_init();

    const char *ssid = cfg.ssid[0]     ? cfg.ssid     : DEFAULT_WIFI_SSID;
    const char *pass = cfg.password[0] ? cfg.password : DEFAULT_WIFI_PASS;

    if (!ssid || ssid[0] == '\0') {
        ESP_LOGE(TAG, "Không có SSID — không thể kết nối WiFi");
        led_status_set_rgb(48, 0, 0);
        while (1) vTaskDelay(pdMS_TO_TICKS(5000));
    }

    bool wifi_ok = wifi_connect_with_retry(ssid, pass, WIFI_MAX_RETRY);
    if (!wifi_ok) {
        ESP_LOGE(TAG, "WiFi kết nối thất bại — khởi động lại sau 5s");
        led_status_set_rgb(48, 0, 0);
        vTaskDelay(pdMS_TO_TICKS(5000));
        esp_restart();
    }
    ESP_LOGI(TAG, "[4/7] WiFi đã kết nối");

    /* 5. Provisioning nếu chưa có token */
    if (!tb_has_token(&cfg)) {
        if (tb_has_prov_credentials(&cfg)) {
            ESP_LOGI(TAG, "[5/7] Chưa có token → thử provisioning...");
            led_status_set_rgb(0, 32, 32); /* Cyan */
            bool prov_ok = tb_provision_device(&cfg);
            if (prov_ok) {
                led_status_set_rgb(0, 48, 0); /* Xanh lá */
                ESP_LOGI(TAG, "[5/7] Provisioning thành công");
            } else {
                led_status_set_rgb(48, 24, 0); /* Cam — cảnh báo */
                ESP_LOGW(TAG, "[5/7] Provisioning thất bại — sẽ thử lại trong MQTT task");
            }
        } else {
            ESP_LOGW(TAG, "[5/7] Không có provisioning credentials, bỏ qua");
        }
    } else {
        ESP_LOGI(TAG, "[5/7] Đã có token, bỏ qua provisioning");
    }

    /* 6. Khởi tạo task manager */
    led_status_set_rgb(0, 16, 32); /* Xanh nhạt — đang start tasks */
    esp_err_t tm_err = task_manager_init(cfg.token[0] ? cfg.token : NULL);
    if (tm_err != ESP_OK) {
        ESP_LOGE(TAG, "Task manager thất bại: %s — reboot sau 3s",
                 esp_err_to_name(tm_err));
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    }
    ESP_LOGI(TAG, "[6/7] Tất cả task đã khởi động");

    /* 7. Đánh dấu firmware hợp lệ (OTA rollback protection) */
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t ota_state;
    if (esp_ota_get_state_partition(running, &ota_state) == ESP_OK &&
        ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();
        ESP_LOGI(TAG, "[7/7] Firmware đã xác nhận hợp lệ (OTA rollback protection)");
    } else {
        ESP_LOGI(TAG, "[7/7] Firmware bình thường (không phải OTA boot)");
    }

    /* In thông tin firmware */
    const esp_app_desc_t *app = esp_app_get_description();
    if (app) {
        ESP_LOGI(TAG, "Firmware: %s v%s | Build: %s %s",
                 app->project_name, app->version, app->date, app->time);
    }

    led_status_white(); /* Trắng — hệ thống đang chạy */
    ESP_LOGI(TAG, "======================================");
    ESP_LOGI(TAG, "  Khởi động hoàn tất!");
    ESP_LOGI(TAG, "======================================");

    /* app_main trả về — FreeRTOS scheduler tiếp quản */
}
