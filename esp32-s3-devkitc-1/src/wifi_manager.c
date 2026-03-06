/*
 * wifi_manager.c — Quản lý kết nối WiFi STA với retry
 */
#include "wifi_manager.h"
#include "led_status.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include <string.h>

static const char *TAG = "wifi_mgr";

static bool                s_netif_ready = false;
static EventGroupHandle_t  s_evt_group   = NULL;

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1

static void wifi_event_handler(void *arg, esp_event_base_t base,
                                int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
        ESP_LOGW(TAG, "WiFi mất kết nối (reason=%d) — đang reconnect...",
                 d ? (int)d->reason : -1);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "IP: " IPSTR, IP2STR(&ev->ip_info.ip));
        if (s_evt_group)
            xEventGroupSetBits(s_evt_group, WIFI_CONNECTED_BIT);
    }
}

static void ensure_netif(void)
{
    if (s_netif_ready) return;
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    s_netif_ready = true;
}

void wifi_manager_init(void)
{
    ensure_netif();
}

bool wifi_connect_with_retry(const char *ssid, const char *password, int max_retry)
{
    if (!ssid || ssid[0] == '\0') {
        ESP_LOGE(TAG, "Không thể kết nối: SSID trống");
        return false;
    }

    ensure_netif();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));

    s_evt_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_cfg = {0};
    strncpy((char *)wifi_cfg.sta.ssid,     ssid,              sizeof(wifi_cfg.sta.ssid) - 1);
    strncpy((char *)wifi_cfg.sta.password, password ? password : "",
            sizeof(wifi_cfg.sta.password) - 1);
    /*
     * WPA_WPA2_PSK: tương thích cả WPA, WPA2, và mạng open (password rỗng).
     * Không dùng WPA2_PSK vì sẽ từ chối mạng WPA hoặc mạng không có password.
     */
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_WPA_WPA2_PSK;
    wifi_cfg.sta.pmf_cfg.capable    = true;
    wifi_cfg.sta.pmf_cfg.required   = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    led_status_set_rgb(32, 24, 0); /* Vàng nhạt — đang kết nối */
    ESP_LOGI(TAG, "Đang kết nối SSID: \"%s\" (tối đa %d lần)...", ssid, max_retry);

    bool connected = false;
    for (int attempt = 1; attempt <= max_retry && !connected; attempt++) {
        EventBits_t bits = xEventGroupWaitBits(
            s_evt_group,
            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
            pdFALSE, pdFALSE,
            pdMS_TO_TICKS(6000));

        if (bits & WIFI_CONNECTED_BIT) {
            connected = true;
        } else {
            ESP_LOGW(TAG, "Thử lần %d/%d...", attempt, max_retry);
        }
    }

    if (connected) {
        led_status_set_rgb(0, 48, 0);
        ESP_LOGI(TAG, "WiFi kết nối thành công");
    } else {
        led_status_set_rgb(48, 0, 0);
        ESP_LOGE(TAG, "WiFi thất bại sau %d lần thử", max_retry);
        esp_wifi_stop();
    }

    vEventGroupDelete(s_evt_group);
    s_evt_group = NULL;
    return connected;
}
