#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

/* ============================================================
 * CẤU TRÚC DỮ LIỆU DÙNG CHUNG CHO TOÀN BỘ HỆ THỐNG
 *
 * Board: GOOUUU Tech ESP32-S3 N16R8 + OV5640
 * Mỗi thiết bị là 1 camera node độc lập, nhận camera_id
 * từ ThingsBoard shared attribute.
 * ============================================================ */

/** Bản tin frame: camera_task → uploader_task */
typedef struct {
    uint8_t *data;          // Con trỏ JPEG (cấp phát trong PSRAM)
    size_t   len;           // Kích thước (bytes)
    uint32_t timestamp_ms;  // Thời điểm chụp (ms kể từ boot)
    uint32_t sequence;      // Số thứ tự frame (tăng dần)
    int      camera_id;     // ID camera (từ g_camera_id, hỗ trợ multi-cam)
} frame_msg_t;

/** Các loại lệnh điều khiển MQTT → Task */
typedef enum {
    MQTT_CMD_NONE = 0,
    MQTT_CMD_CAMERA_RESOLUTION,   // Đổi độ phân giải camera
    MQTT_CMD_CAMERA_QUALITY,      // Đổi chất lượng JPEG
    MQTT_CMD_CAPTURE_INTERVAL,    // Đổi tần suất chụp (ms)
    MQTT_CMD_REBOOT,              // Khởi động lại thiết bị
    MQTT_CMD_OTA_START,           // Bắt đầu OTA update
} mqtt_cmd_type_t;

/** Bản tin lệnh MQTT (MQTT task → các task khác) */
typedef struct {
    mqtt_cmd_type_t cmd;
    int request_id;             // RPC request ID để gửi response về TB
    union {
        struct { char url[256]; }   ota;
        struct { int framesize; }   resolution;
        struct { int quality; }     quality;
        struct { int interval_ms; } interval;
    } payload;
} mqtt_cmd_msg_t;

/** Dữ liệu telemetry sức khỏe thiết bị */
typedef struct {
    uint32_t free_heap;         // Heap tự do (bytes)
    uint32_t min_free_heap;     // Heap nhỏ nhất từ trước đến nay (bytes)
    int8_t   wifi_rssi;         // Cường độ sóng WiFi (dBm)
    uint32_t frame_count;       // Tổng frame đã chụp
    uint32_t send_success;      // Tổng lần upload thành công
    uint32_t send_fail;         // Tổng lần upload thất bại
    uint32_t uptime_sec;        // Thời gian hoạt động (giây)
    bool     camera_ok;         // Camera đang hoạt động
    bool     mqtt_connected;    // MQTT đang kết nối
    bool     net_error;         // Đang có lỗi mạng
    bool     upload_ok;         // Lần upload cuối thành công
    int      last_http_code;    // HTTP status code lần upload cuối
    uint32_t latency_ms;        // Độ trễ upload cuối (ms)
} health_telemetry_t;

/** Snapshot trạng thái đèn giao thông */
typedef struct {
    uint8_t  state;     // 0=red, 1=yellow, 2=green
    uint8_t  mode;      // 0=normal, 1=emg_red, 2=emg_green
    uint32_t state_ms;  // Thời gian đã giữ pha này (ms)
} tl_telemetry_t;

/** Loại bản tin telemetry */
typedef enum {
    TELEMETRY_HEALTH = 0,
    TELEMETRY_STATUS,
    TELEMETRY_EVENT,
    TELEMETRY_TRAFFIC_LIGHT,
} telemetry_type_t;

/** Bản tin telemetry (health/traffic task → MQTT task) */
typedef struct {
    telemetry_type_t type;
    union {
        health_telemetry_t              health;
        tl_telemetry_t                  traffic;
        struct { char status[32]; }     status;
        struct { char key[48];
                 char value[96]; }      event;  // key=value pair (không phải JSON)
    } data;
} telemetry_msg_t;

/* ---- Độ sâu queue ----------------------------------------- */
#define FRAME_QUEUE_DEPTH       3
#define MQTT_CMD_QUEUE_DEPTH    4
#define TELEMETRY_QUEUE_DEPTH   8

/* ---- Stack size (bytes) — ESP32-S3 cần lớn hơn cho TLS --- */
#define CAMERA_TASK_STACK_SIZE    6144
#define UPLOADER_TASK_STACK_SIZE  12288
#define MQTT_TASK_STACK_SIZE      12288
#define HEALTH_TASK_STACK_SIZE    4096
#define BUTTON_TASK_STACK_SIZE    2048

/* ---- Độ ưu tiên task (cao hơn = ưu tiên hơn) ------------- */
#define CAMERA_TASK_PRIORITY      7
#define UPLOADER_TASK_PRIORITY    6
#define MQTT_TASK_PRIORITY        5
#define HEALTH_TASK_PRIORITY      4
#define BUTTON_TASK_PRIORITY      8

/* ---- Khoảng thời gian (ms) -------------------------------- */
#define HEALTH_CHECK_INTERVAL_MS  5000
#define TELEMETRY_INTERVAL_MS     30000
#define WATCHDOG_TIMEOUT_SEC      60

/* ---- Retry HTTP ------------------------------------------- */
#define HTTP_MAX_RETRY_COUNT      3
#define HTTP_RETRY_DELAY_MS       1000
