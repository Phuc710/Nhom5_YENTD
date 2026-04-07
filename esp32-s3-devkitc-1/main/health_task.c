/*
 * health_task.c - Device health telemetry task.
 */
#include "task_manager.h"
#include "mqtt_app.h"
/* traffic_light.h removed — traffic light moved to ESP32_PCB */

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "health";

/** Map trạng thái runtime → device_state_t enum chính thức */
static device_state_t resolve_device_state(bool mqtt_connected)
{
    if (mqtt_app_is_ota_active()) {
        return DEVICE_STATE_OTA;
    }
    if (!g_camera_ok) {
        return DEVICE_STATE_ERROR;
    }
    if (mqtt_app_is_degraded()) {
        return DEVICE_STATE_DEGRADED;
    }
    if (!mqtt_connected && task_manager_is_system_ready()) {
        return DEVICE_STATE_RECONNECTING;
    }
    if (task_manager_is_system_ready()) {
        return DEVICE_STATE_READY;
    }
    return task_manager_get_device_state();
}

void health_task(void *pvParameter)
{
    (void)pvParameter;

    TickType_t last_telem_tick = xTaskGetTickCount();

    while (g_system_running) {
        vTaskDelay(pdMS_TO_TICKS(HEALTH_CHECK_INTERVAL_MS));

        uint32_t free_heap  = esp_get_free_heap_size();
        uint32_t min_heap   = esp_get_minimum_free_heap_size();
        int8_t   rssi       = get_wifi_rssi();
        uint32_t uptime     = (uint32_t)(esp_timer_get_time() / 1000000ULL);
        int64_t  now_us     = esp_timer_get_time();
        bool     mqtt_ok    = mqtt_app_is_connected();
        bool     degraded   = mqtt_app_is_degraded();

        device_state_t ds = resolve_device_state(mqtt_ok);

        TickType_t now       = xTaskGetTickCount();
        /* [MQTT-FIRST] Gửi info chuyên sâu mỗi 60s, còn hằng giây đã dồn vào Traffic Light */
        uint32_t interval_ms = (g_telemetry_interval_ms > 60000)
                               ? g_telemetry_interval_ms
                               : 60000; 


        if ((now - last_telem_tick) >= pdMS_TO_TICKS(interval_ms)) {
            last_telem_tick = now;

            telemetry_msg_t    msg = { .type = TELEMETRY_HEALTH };
            health_telemetry_t *h  = &msg.data.health;

            h->free_heap            = free_heap;
            h->min_free_heap        = min_heap;
            h->wifi_rssi            = rssi;
            h->uptime_sec           = uptime;
            h->camera_ok            = g_camera_ok;
            h->mqtt_connected       = mqtt_ok;
            h->stream_ok            = false;
            h->backend_degraded     = degraded;
            h->wifi_disconnect_count= g_wifi_disconnect_count;
            h->last_seen_ts         = now_us;
            h->light_state          = 0; /* camera không có đèn — xem ESP32_PCB telemetry */
            h->cpu_temp             = g_cpu_temp;
            snprintf(h->device_state, sizeof(h->device_state),
                     "%s", device_state_to_str(ds));

            if (g_telemetry_queue &&
                xQueueSend(g_telemetry_queue, &msg, 0) != pdTRUE) {
                ESP_LOGW(TAG, "HEALTH | queue đầy");
            }
        }
    }

    ESP_LOGI(TAG, "HEALTH | dừng");
    vTaskDelete(NULL);
}
