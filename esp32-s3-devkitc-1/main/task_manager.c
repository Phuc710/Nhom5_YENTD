/*
 * task_manager.c - Khoi tao queue va start cac FreeRTOS task.
 * Giu lai luong cu voi ThingsBoard/MQTT/OTA/traffic light va HTTP stream.
 */
#include "task_manager.h"

#include <string.h>

#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "task_common.h"
#include "traffic_light.h"

static const char *TAG = "task_mgr";

#ifndef DEFAULT_CAPTURE_INTERVAL_MS
#error "DEFAULT_CAPTURE_INTERVAL_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef DEFAULT_CAMERA_ID
#error "DEFAULT_CAMERA_ID chua duoc dinh nghia. Dat trong platformio.ini."
#endif

void camera_task(void *pvParameter);
void mqtt_task(void *pvParameter);
void health_task(void *pvParameter);
void button_task(void *pvParameter);

TaskHandle_t g_camera_task_handle = NULL;
TaskHandle_t g_mqtt_task_handle = NULL;
TaskHandle_t g_health_task_handle = NULL;
TaskHandle_t g_button_task_handle = NULL;
TaskHandle_t g_traffic_task_handle = NULL;

QueueHandle_t g_mqtt_cmd_queue = NULL;
QueueHandle_t g_telemetry_queue = NULL;
SemaphoreHandle_t g_latest_frame_mutex = NULL;

volatile uint32_t g_capture_interval_ms = DEFAULT_CAPTURE_INTERVAL_MS;
volatile uint32_t g_stream_client_count = 0;
volatile uint32_t g_frame_count = 0;
volatile int g_camera_id = DEFAULT_CAMERA_ID;
volatile bool g_system_running = true;

volatile bool g_camera_ok = false;
volatile uint32_t g_wifi_disconnect_count = 0; /* Tang moi lan WiFi STA mat ket noi */
volatile uint32_t g_telemetry_interval_ms = TELEMETRY_INTERVAL_MS; /* Override tu ThingsBoard */
volatile float    g_cpu_temp = 0.0f;

uint8_t *g_latest_buf = NULL;
size_t g_latest_len = 0;

esp_err_t task_manager_init(const char *token)
{
    ESP_LOGI(TAG, "⚙️ Đang khởi tạo Task Manager...");

    g_stream_client_count = 0;

    g_mqtt_cmd_queue = xQueueCreate(MQTT_CMD_QUEUE_DEPTH, sizeof(mqtt_cmd_msg_t));
    if (!g_mqtt_cmd_queue) {
        ESP_LOGE(TAG, "❌ Tạo hàng đợi MQTT Cmd thất bại");
        return ESP_ERR_NO_MEM;
    }

    g_telemetry_queue = xQueueCreate(TELEMETRY_QUEUE_DEPTH, sizeof(telemetry_msg_t));
    if (!g_telemetry_queue) {
        ESP_LOGE(TAG, "❌ Tạo hàng đợi Telemetry thất bại");
        return ESP_ERR_NO_MEM;
    }

    g_latest_frame_mutex = xSemaphoreCreateMutex();
    if (!g_latest_frame_mutex) {
        ESP_LOGE(TAG, "❌ Tạo Frame Mutex thất bại");
        return ESP_ERR_NO_MEM;
    }

    extern camera_config_t goouuu_camera_config_default(void);
    camera_config_t cam_cfg = goouuu_camera_config_default();
    esp_err_t cam_err = esp_camera_init(&cam_cfg);
    if (cam_err != ESP_OK) {
        ESP_LOGW(TAG, "⚠️ Khởi tạo Camera thất bại (0x%x)", cam_err);
        g_camera_ok = false;
    } else {
        g_camera_ok = true;
        ESP_LOGI(TAG, "📸 Camera đã sẵn sàng");
    }

    traffic_light_init();

    char *token_copy = token && token[0] ? strdup(token) : NULL;
    BaseType_t ret;

    ret = xTaskCreate(camera_task, "cam_task", CAMERA_TASK_STACK_SIZE,
                      NULL, CAMERA_TASK_PRIORITY, &g_camera_task_handle);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "❌ Tạo Task Camera thất bại");
        return ESP_FAIL;
    }

    ret = xTaskCreate(mqtt_task, "mqtt_task", MQTT_TASK_STACK_SIZE,
                      token_copy, MQTT_TASK_PRIORITY, &g_mqtt_task_handle);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "❌ Tạo Task MQTT thất bại");
        return ESP_FAIL;
    }

    ret = xTaskCreate(health_task, "health", HEALTH_TASK_STACK_SIZE,
                      NULL, HEALTH_TASK_PRIORITY, &g_health_task_handle);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "❌ Tạo Task Health thất bại");
        return ESP_FAIL;
    }

    ret = xTaskCreate(button_task, "btn_task", BUTTON_TASK_STACK_SIZE,
                      NULL, BUTTON_TASK_PRIORITY, &g_button_task_handle);
    if (ret != pdPASS) {
        ESP_LOGW(TAG, "⚠️ Tạo Task Button thất bại (không bắt buộc)");
    }

    ret = xTaskCreate(traffic_light_task, "tl_task", 3072,
                      NULL, 6, &g_traffic_task_handle);
    if (ret != pdPASS) {
        ESP_LOGW(TAG, "Tao traffic light task that bai");
    }

    ESP_LOGI(TAG, "✅ Tất cả các Task đã hoạt động");
    return ESP_OK;
}

void task_manager_stop(void)
{
    ESP_LOGW(TAG, "Dang dung tat ca task...");
    g_system_running = false;
    g_stream_client_count = 0;
    vTaskDelay(pdMS_TO_TICKS(500));

    if (g_camera_task_handle) {
        vTaskDelete(g_camera_task_handle);
    }
    if (g_mqtt_task_handle) {
        vTaskDelete(g_mqtt_task_handle);
    }
    if (g_health_task_handle) {
        vTaskDelete(g_health_task_handle);
    }
    if (g_button_task_handle) {
        vTaskDelete(g_button_task_handle);
    }
    if (g_traffic_task_handle) {
        vTaskDelete(g_traffic_task_handle);
    }
    if (g_mqtt_cmd_queue) {
        vQueueDelete(g_mqtt_cmd_queue);
    }
    if (g_telemetry_queue) {
        vQueueDelete(g_telemetry_queue);
    }
}

void update_latest_frame_shared(const uint8_t *data, size_t len)
{
    if (!g_latest_frame_mutex || !data || len == 0) {
        return;
    }

    if (xSemaphoreTake(g_latest_frame_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        if (g_latest_buf) {
            heap_caps_free(g_latest_buf);
            g_latest_buf = NULL;
            g_latest_len = 0;
        }

        g_latest_buf = heap_caps_malloc(len, MALLOC_CAP_SPIRAM);
        if (g_latest_buf) {
            memcpy(g_latest_buf, data, len);
            g_latest_len = len;
        }

        xSemaphoreGive(g_latest_frame_mutex);
    }
}

int8_t get_wifi_rssi(void)
{
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        return ap.rssi;
    }
    return 0;
}

void task_manager_report_event(const char *key, const char *value)
{
    if (!g_telemetry_queue) {
        return;
    }

    telemetry_msg_t msg = { .type = TELEMETRY_EVENT };
    strncpy(msg.data.event.key, key ? key : "event", sizeof(msg.data.event.key) - 1);
    strncpy(msg.data.event.value, value ? value : "", sizeof(msg.data.event.value) - 1);

    xQueueSend(g_telemetry_queue, &msg, 0);
}
