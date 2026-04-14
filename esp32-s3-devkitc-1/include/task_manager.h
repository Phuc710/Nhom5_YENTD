#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "task_common.h"
#include "app_config.h"

/* Task handles */
extern TaskHandle_t g_camera_task_handle;
extern TaskHandle_t g_mqtt_task_handle;
extern TaskHandle_t g_health_task_handle;
extern TaskHandle_t g_button_task_handle;
extern TaskHandle_t g_traffic_task_handle;

/* Queue handles */
extern QueueHandle_t g_mqtt_cmd_queue;
extern QueueHandle_t g_telemetry_queue;

/* Shared frame state */
extern SemaphoreHandle_t g_latest_frame_mutex;
extern uint8_t *g_latest_buf;
extern size_t g_latest_len;

/* Shared runtime state */
extern volatile uint32_t g_capture_interval_ms;
extern volatile uint32_t g_stream_client_count;
extern volatile uint32_t g_frame_count;
extern volatile int g_camera_id;
extern volatile bool g_system_running;
extern volatile bool g_system_ready;
extern volatile device_state_t g_device_state;
extern volatile uint32_t g_telemetry_interval_ms; /* Override tu ThingsBoard shared attr */

extern volatile bool g_camera_ok;
extern volatile uint32_t g_wifi_disconnect_count; /* So lan mat ket noi WiFi tu boot */
extern volatile float    g_cpu_temp;              /* Nhiet do CPU hien tai (deg C) */

esp_err_t task_manager_init(const char *token);
esp_err_t task_manager_start_post_connect_services(void);
void task_manager_stop(void);
void update_latest_frame_shared(const uint8_t *data, size_t len);
int8_t get_wifi_rssi(void);
void task_manager_report_event(const char *key, const char *value);
void task_manager_set_system_ready(bool ready);
bool task_manager_is_system_ready(void);
void task_manager_set_device_state(device_state_t state);
device_state_t task_manager_get_device_state(void);
bool task_manager_post_connect_services_started(void);
