#pragma once

#include <stdbool.h>
#include <stdint.h>

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

/** Snapshot trạng thái đèn giao thông */
typedef struct {
    uint8_t  state;     /* 0=red, 1=yellow, 2=green */
    uint8_t  mode;      /* 0=normal, 1=emg_red, 2=emg_green */
    uint32_t state_ms;  /* Thời gian đã giữ pha này (ms) */
    uint32_t phase_duration_ms; /* Tổng thời gian của pha hiện tại (ms) */
    uint32_t phase_start_ms;    /* Mốc bắt đầu pha hiện tại (ms từ boot) */
    uint32_t remain_sec;        /* Số giây còn lại của pha hiện tại */
    uint32_t red_ms;            /* Cấu hình pha đỏ hiện tại (ms) */
    uint32_t yellow_ms;         /* Cấu hình pha vàng hiện tại (ms) */
    uint32_t green_ms;          /* Cấu hình pha xanh hiện tại (ms) */
    bool     red_on;            /* true nếu đèn đỏ đang sáng */
    bool     yellow_on;         /* true nếu đèn vàng đang sáng */
    bool     green_on;          /* true nếu đèn xanh đang sáng */
} tl_telemetry_t;

/** Các loại lệnh điều khiển MQTT -> Task */
typedef enum {
    MQTT_CMD_NONE = 0,
    MQTT_CMD_CAMERA_RESOLUTION,   /* Đổi độ phân giải camera */
    MQTT_CMD_CAMERA_QUALITY,      /* Đổi chất lượng JPEG */
    MQTT_CMD_CAPTURE_INTERVAL,    /* Đổi tần suất chụp (ms) */
    MQTT_CMD_REBOOT,              /* Khởi động lại thiết bị */
    MQTT_CMD_OTA_START,           /* Bắt đầu OTA update */
} mqtt_cmd_type_t;

/** Bản tin lệnh MQTT (MQTT task -> các task khác) */
typedef struct {
    mqtt_cmd_type_t cmd;
    int request_id; /* RPC request ID để gửi response về ThingsBoard */
    union {
        struct { char url[256]; }   ota;
        struct { int framesize; }   resolution;
        struct { int quality; }     quality;
        struct { int interval_ms; } interval;
    } payload;
} mqtt_cmd_msg_t;

/** Dữ liệu telemetry sức khỏe thiết bị */
typedef struct {
    uint32_t free_heap;              /* Heap tự do (bytes) */
    uint32_t min_free_heap;          /* Heap nhỏ nhất từ trước đến nay (bytes) */
    int8_t   wifi_rssi;              /* Cường độ sóng WiFi (dBm) */
    uint32_t uptime_sec;             /* Thời gian hoạt động (giây) */
    bool     camera_ok;              /* Camera đang hoạt động */
    bool     mqtt_connected;         /* MQTT đang kết nối */
    uint32_t wifi_disconnect_count;  /* Số lần mất WiFi từ khi boot */
    char     device_state[16];       /* "boot" | "running" | "ota" | "error" */
    int64_t  last_seen_ts;           /* Microseconds từ boot (esp_timer_get_time) */
    uint8_t  light_state;            /* 0=red, 1=yellow, 2=green */
    float    cpu_temp;               /* Nhiệt độ CPU (degrees C) */
} health_telemetry_t;

/** Loại bản tin telemetry */
typedef enum {
    TELEMETRY_HEALTH = 0,
    TELEMETRY_STATUS,
    TELEMETRY_EVENT,
    TELEMETRY_TRAFFIC_LIGHT,
} telemetry_type_t;

/** Bản tin telemetry (health/traffic task -> MQTT task) */
typedef struct {
    telemetry_type_t type;
    union {
        health_telemetry_t          health;
        tl_telemetry_t              traffic;
        struct { char status[32]; } status;
        struct {
            char key[48];
            char value[96];
        } event; /* key=value pair (không phải JSON) */
    } data;
} telemetry_msg_t;

/* ---- Độ sâu queue ---------------------------------------- */
#define MQTT_CMD_QUEUE_DEPTH    4
#define TELEMETRY_QUEUE_DEPTH   8

/* ---- Stack size (bytes) ---------------------------------- */
#define CAMERA_TASK_STACK_SIZE    6144
#define MQTT_TASK_STACK_SIZE      12288
#define HEALTH_TASK_STACK_SIZE    4096
#define BUTTON_TASK_STACK_SIZE    2048

/* ---- Độ ưu tiên task ------------------------------------- */
#define CAMERA_TASK_PRIORITY      7
#define MQTT_TASK_PRIORITY        5
#define HEALTH_TASK_PRIORITY      4
#define BUTTON_TASK_PRIORITY      8

/* ---- Khoảng thời gian (ms) ------------------------------- */
#ifndef HEALTH_CHECK_INTERVAL_MS
#define HEALTH_CHECK_INTERVAL_MS  5000
#endif
#ifndef TELEMETRY_INTERVAL_MS
#define TELEMETRY_INTERVAL_MS     30000
#endif
#ifndef WATCHDOG_TIMEOUT_SEC
#error "WATCHDOG_TIMEOUT_SEC chua duoc dinh nghia. Dat trong platformio.ini."
#endif
