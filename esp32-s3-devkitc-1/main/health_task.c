/*
 * health_task.c - Theo doi suc khoe thiet bi va gui telemetry len ThingsBoard.
 */
#include "task_manager.h"
#include "mqtt_app.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "health";

extern volatile bool     g_last_upload_ok;
extern volatile int      g_last_http_code;
extern volatile uint32_t g_last_latency_ms;

void health_task(void *pvParameter)
{
    (void)pvParameter;
    ESP_LOGI(TAG, "Task sức khỏe khởi động");

    TickType_t last_telem_tick = xTaskGetTickCount();

    while (g_system_running) {
        vTaskDelay(pdMS_TO_TICKS(HEALTH_CHECK_INTERVAL_MS));

        uint32_t free_heap = esp_get_free_heap_size();
        uint32_t min_heap  = esp_get_minimum_free_heap_size();
        int8_t   rssi      = get_wifi_rssi();
        uint32_t uptime    = (uint32_t)(esp_timer_get_time() / 1000000ULL);

        ESP_LOGI(
            TAG,
            "Heap:%lu MinHeap:%lu RSSI:%d dBm Uptime:%lus Frame:%lu OK:%lu Fail:%lu Camera:%s",
            (unsigned long)free_heap,
            (unsigned long)min_heap,
            rssi,
            (unsigned long)uptime,
            (unsigned long)g_frame_count,
            (unsigned long)g_send_success,
            (unsigned long)g_send_fail,
            g_camera_ok ? "OK" : "LỖI"
        );

        TickType_t now = xTaskGetTickCount();
        if ((now - last_telem_tick) >= pdMS_TO_TICKS(TELEMETRY_INTERVAL_MS)) {
            last_telem_tick = now;

            telemetry_msg_t msg = { .type = TELEMETRY_HEALTH };
            health_telemetry_t *h = &msg.data.health;

            h->free_heap      = free_heap;
            h->min_free_heap  = min_heap;
            h->wifi_rssi      = rssi;
            h->frame_count    = g_frame_count;
            h->send_success   = g_send_success;
            h->send_fail      = g_send_fail;
            h->uptime_sec     = uptime;
            h->camera_ok      = g_camera_ok;
            h->mqtt_connected = mqtt_app_is_connected();
            h->net_error      = g_net_error;
            h->upload_ok      = g_last_upload_ok;
            h->last_http_code = g_last_http_code;
            h->latency_ms     = g_last_latency_ms;

            if (g_telemetry_queue &&
                xQueueSend(g_telemetry_queue, &msg, 0) != pdTRUE) {
                ESP_LOGW(TAG, "Telemetry queue đầy");
            }
        }
    }

    ESP_LOGI(TAG, "Task sức khỏe kết thúc");
    vTaskDelete(NULL);
}
