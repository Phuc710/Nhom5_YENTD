/*
 * health_task.c - Device health telemetry task.
 */
#include "task_manager.h"
#include "mqtt_app.h"
#include "traffic_light.h"

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "health";

void health_task(void *pvParameter)
{
    (void)pvParameter;

    TickType_t last_telem_tick = xTaskGetTickCount();

    while (g_system_running) {
        vTaskDelay(pdMS_TO_TICKS(HEALTH_CHECK_INTERVAL_MS));

        uint32_t free_heap = esp_get_free_heap_size();
        uint32_t min_heap = esp_get_minimum_free_heap_size();
        int8_t rssi = get_wifi_rssi();
        uint32_t uptime = (uint32_t)(esp_timer_get_time() / 1000000ULL);
        int64_t now_us = esp_timer_get_time();
        bool is_mqtt_connected = mqtt_app_is_connected();
        char device_state[16];

        if (mqtt_app_is_ota_active()) {
            snprintf(device_state, sizeof(device_state), "ota");
        } else if (!g_camera_ok) {
            snprintf(device_state, sizeof(device_state), "error");
        } else if (!is_mqtt_connected) {
            snprintf(device_state, sizeof(device_state), "wifi_connecting");
        } else {
            snprintf(device_state, sizeof(device_state), "running");
        }

        TickType_t now = xTaskGetTickCount();
        uint32_t interval_ms = (g_telemetry_interval_ms > 0)
                               ? g_telemetry_interval_ms
                               : TELEMETRY_INTERVAL_MS;
        if ((now - last_telem_tick) >= pdMS_TO_TICKS(interval_ms)) {
            last_telem_tick = now;

            tl_status_t tl = traffic_light_get_status();
            telemetry_msg_t msg = { .type = TELEMETRY_HEALTH };
            health_telemetry_t *h = &msg.data.health;

            h->free_heap = free_heap;
            h->min_free_heap = min_heap;
            h->wifi_rssi = rssi;
            h->uptime_sec = uptime;
            h->camera_ok = g_camera_ok;
            h->mqtt_connected = is_mqtt_connected;
            h->wifi_disconnect_count = g_wifi_disconnect_count;
            h->last_seen_ts = now_us;
            h->light_state = (uint8_t)tl.state;
            h->cpu_temp = 0.0f; /* Cảm biến nhiệt độ không dùng cho camera AI */
            snprintf(h->device_state, sizeof(h->device_state), "%s", device_state);

            if (g_telemetry_queue &&
                xQueueSend(g_telemetry_queue, &msg, 0) != pdTRUE) {
                ESP_LOGW(TAG, "HEALTH | queue đầy");
            }
        }
    }

    ESP_LOGI(TAG, "HEALTH | dừng");
    vTaskDelete(NULL);
}
