/*
 * health_task.c - Device health telemetry task.
 */
#include "task_manager.h"
#include "mqtt_app.h"
#include "traffic_light.h"

#include "driver/temperature_sensor.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "health";

void health_task(void *pvParameter)
{
    (void)pvParameter;

    temperature_sensor_handle_t temp_sensor = NULL;
    temperature_sensor_config_t temp_cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(-10, 80);
    if (temperature_sensor_install(&temp_cfg, &temp_sensor) == ESP_OK) {
        temperature_sensor_enable(temp_sensor);
        ESP_LOGI(TAG, "HEALTH | sensor ready");
    }

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

        if (temp_sensor) {
            float tsens_out = 0.0f;
            if (temperature_sensor_get_celsius(temp_sensor, &tsens_out) == ESP_OK) {
                g_cpu_temp = tsens_out;
            }
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
            h->cpu_temp = g_cpu_temp;
            snprintf(h->device_state, sizeof(h->device_state), "%s", device_state);

            if (g_telemetry_queue &&
                xQueueSend(g_telemetry_queue, &msg, 0) != pdTRUE) {
                ESP_LOGW(TAG, "HEALTH | queue full");
            }
        }
    }

    ESP_LOGI(TAG, "HEALTH | stop");
    vTaskDelete(NULL);
}
