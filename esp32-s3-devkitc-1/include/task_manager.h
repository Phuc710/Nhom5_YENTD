#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_err.h"
#include "task_common.h"
#include "app_config.h"

/* ============================================================
 * TASK MANAGER — Bộ điều phối trung tâm FreeRTOS tasks
 * Board: GOOUUU Tech ESP32-S3 N16R8 + OV5640
 * ============================================================ */

/* ---------- Task handles ---------------------------------- */
extern TaskHandle_t g_camera_task_handle;
extern TaskHandle_t g_uploader_task_handle;
extern TaskHandle_t g_mqtt_task_handle;
extern TaskHandle_t g_health_task_handle;
extern TaskHandle_t g_button_task_handle;
extern TaskHandle_t g_traffic_task_handle;

/* ---------- Queue handles --------------------------------- */
extern QueueHandle_t g_frame_queue;       // camera → uploader
extern QueueHandle_t g_mqtt_cmd_queue;    // mqtt   → tasks
extern QueueHandle_t g_telemetry_queue;   // health/traffic → mqtt

/* ---------- Mutex frame buffer (HTTP server tương lai) ---- */
extern SemaphoreHandle_t g_latest_frame_mutex;

/* ---------- Trạng thái chia sẻ (volatile) ---------------- */
extern volatile uint32_t g_capture_interval_ms; // Tần suất chụp (ms)
extern volatile bool     g_save_img;            // Lưu ảnh lên backend?
extern volatile int      g_camera_id;           // Camera ID hiện tại
extern volatile uint16_t g_frames_per_upload;   // Số frame upload tối đa/epoch
extern volatile uint32_t g_frames_upload_epoch; // Reset bộ đếm MinIO khi tăng
extern volatile bool     g_system_running;      // Cờ thoát task

/* ---------- Thống kê -------------------------------------- */
extern volatile uint32_t g_frame_count;   // Tổng frame đã chụp
extern volatile uint32_t g_send_success;  // Tổng upload thành công
extern volatile uint32_t g_send_fail;     // Tổng upload thất bại
extern volatile bool     g_camera_ok;     // Camera có lấy được frame?
extern volatile bool     g_net_error;     // Lỗi mạng liên tiếp?

/* ---------- Frame buffer mới nhất (HTTP server) ----------- */
extern uint8_t *g_latest_buf;
extern size_t   g_latest_len;

/* ---------- API ------------------------------------------- */

/** Khởi tạo queues, camera, traffic light GPIO, start tất cả tasks */
esp_err_t task_manager_init(const char *token);

/** Dừng tất cả task (graceful shutdown) */
void task_manager_stop(void);

/** Cập nhật frame buffer mới nhất (bảo vệ bởi mutex) */
void update_latest_frame_shared(const uint8_t *data, size_t len);

/** Lấy RSSI WiFi hiện tại (dBm) */
int8_t get_wifi_rssi(void);

/** Gửi event lên MQTT telemetry queue (key + value thuần, không phải JSON) */
void task_manager_report_event(const char *key, const char *value);
