/*
 * task_manager.c - Khoi tao queue va start tat ca FreeRTOS task.
 */
#include "task_manager.h"
#include "task_common.h"
#include "traffic_light.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include <string.h>

static const char *TAG = "task_mgr";

#ifndef DEFAULT_CAPTURE_INTERVAL_MS
#define DEFAULT_CAPTURE_INTERVAL_MS 1000
#endif
#ifndef DEFAULT_SAVE_IMG
#define DEFAULT_SAVE_IMG 1
#endif
#ifndef DEFAULT_CAMERA_ID
#define DEFAULT_CAMERA_ID 1
#endif

void camera_task(void *pvParameter);
void uploader_task(void *pvParameter);
void mqtt_task(void *pvParameter);
void health_task(void *pvParameter);
void button_task(void *pvParameter);

TaskHandle_t g_camera_task_handle   = NULL;
TaskHandle_t g_uploader_task_handle = NULL;
TaskHandle_t g_mqtt_task_handle     = NULL;
TaskHandle_t g_health_task_handle   = NULL;
TaskHandle_t g_button_task_handle   = NULL;
TaskHandle_t g_traffic_task_handle  = NULL;

QueueHandle_t     g_frame_queue         = NULL;
QueueHandle_t     g_mqtt_cmd_queue      = NULL;
QueueHandle_t     g_telemetry_queue     = NULL;
SemaphoreHandle_t g_latest_frame_mutex  = NULL;

volatile uint32_t g_capture_interval_ms = DEFAULT_CAPTURE_INTERVAL_MS;
volatile bool     g_save_img            = (DEFAULT_SAVE_IMG != 0);
volatile int      g_camera_id           = DEFAULT_CAMERA_ID;
volatile uint16_t g_frames_per_upload   = APP_CONFIG_DEFAULT_FRAMES_PER_UPLOAD;
volatile uint32_t g_frames_upload_epoch = 0;
volatile bool     g_system_running      = true;

volatile uint32_t g_frame_count   = 0;
volatile uint32_t g_send_success  = 0;
volatile uint32_t g_send_fail     = 0;
volatile bool     g_camera_ok     = false;
volatile bool     g_net_error     = false;

uint8_t *g_latest_buf = NULL;
size_t   g_latest_len = 0;

esp_err_t task_manager_init(const char *token)
{
    ESP_LOGI(TAG, "Khởi tạo task manager...");

    g_frame_queue = xQueueCreate(FRAME_QUEUE_DEPTH, sizeof(frame_msg_t));
    if (!g_frame_queue) {
        ESP_LOGE(TAG, "Tạo frame queue thất bại");
        return ESP_ERR_NO_MEM;
    }

    g_mqtt_cmd_queue = xQueueCreate(MQTT_CMD_QUEUE_DEPTH, sizeof(mqtt_cmd_msg_t));
    if (!g_mqtt_cmd_queue) {
        ESP_LOGE(TAG, "Tạo MQTT cmd queue thất bại");
        return ESP_ERR_NO_MEM;
    }

    g_telemetry_queue = xQueueCreate(TELEMETRY_QUEUE_DEPTH, sizeof(telemetry_msg_t));
    if (!g_telemetry_queue) {
        ESP_LOGE(TAG, "Tạo telemetry queue thất bại");
        return ESP_ERR_NO_MEM;
    }

    g_latest_frame_mutex = xSemaphoreCreateMutex();
    if (!g_latest_frame_mutex) {
        ESP_LOGE(TAG, "Tạo frame mutex thất bại");
        return ESP_ERR_NO_MEM;
    }

    extern camera_config_t goouuu_camera_config_default(void);
    camera_config_t cam_cfg = goouuu_camera_config_default();
    esp_err_t cam_err = esp_camera_init(&cam_cfg);
    if (cam_err != ESP_OK) {
        ESP_LOGW(TAG, "Khởi tạo camera thất bại (0x%x) - task camera vẫn chạy để báo lỗi runtime", cam_err);
        g_camera_ok = false;
    } else {
        g_camera_ok = true;
        ESP_LOGI(TAG, "Camera đã khởi tạo thành công");
    }

    traffic_light_init();

    char *token_copy = token && token[0] ? strdup(token) : NULL;
    BaseType_t ret;

    ret = xTaskCreate(camera_task, "cam_task", CAMERA_TASK_STACK_SIZE,
                      NULL, CAMERA_TASK_PRIORITY, &g_camera_task_handle);
    if (ret != pdPASS) { ESP_LOGE(TAG, "Tạo camera task thất bại"); return ESP_FAIL; }

    ret = xTaskCreate(uploader_task, "uploader", UPLOADER_TASK_STACK_SIZE,
                      NULL, UPLOADER_TASK_PRIORITY, &g_uploader_task_handle);
    if (ret != pdPASS) { ESP_LOGE(TAG, "Tạo uploader task thất bại"); return ESP_FAIL; }

    ret = xTaskCreate(mqtt_task, "mqtt_task", MQTT_TASK_STACK_SIZE,
                      token_copy, MQTT_TASK_PRIORITY, &g_mqtt_task_handle);
    if (ret != pdPASS) { ESP_LOGE(TAG, "Tạo MQTT task thất bại"); return ESP_FAIL; }

    ret = xTaskCreate(health_task, "health", HEALTH_TASK_STACK_SIZE,
                      NULL, HEALTH_TASK_PRIORITY, &g_health_task_handle);
    if (ret != pdPASS) { ESP_LOGE(TAG, "Tạo health task thất bại"); return ESP_FAIL; }

    ret = xTaskCreate(button_task, "btn_task", BUTTON_TASK_STACK_SIZE,
                      NULL, BUTTON_TASK_PRIORITY, &g_button_task_handle);
    if (ret != pdPASS) { ESP_LOGW(TAG, "Tạo button task thất bại (không bắt buộc)"); }

    ret = xTaskCreate(traffic_light_task, "tl_task", 3072,
                      NULL, 6, &g_traffic_task_handle);
    if (ret != pdPASS) { ESP_LOGW(TAG, "Tạo traffic light task thất bại"); }

    ESP_LOGI(TAG, "Tất cả task đã khởi động");
    return ESP_OK;
}

void task_manager_stop(void)
{
    ESP_LOGW(TAG, "Đang dừng tất cả task...");
    g_system_running = false;
    vTaskDelay(pdMS_TO_TICKS(500));

    if (g_camera_task_handle)   vTaskDelete(g_camera_task_handle);
    if (g_uploader_task_handle) vTaskDelete(g_uploader_task_handle);
    if (g_mqtt_task_handle)     vTaskDelete(g_mqtt_task_handle);
    if (g_health_task_handle)   vTaskDelete(g_health_task_handle);
    if (g_button_task_handle)   vTaskDelete(g_button_task_handle);
    if (g_traffic_task_handle)  vTaskDelete(g_traffic_task_handle);
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
