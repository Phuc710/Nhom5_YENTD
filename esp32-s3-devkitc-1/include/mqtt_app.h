#pragma once

#include <stdbool.h>
#include "task_common.h"

/* MQTT topic cho ThingsBoard */
#define TB_TOPIC_TELEMETRY          "v1/devices/me/telemetry"
#define TB_TOPIC_ATTRIBUTES         "v1/devices/me/attributes"
#define TB_TOPIC_ATTRIBUTES_REQ     "v1/devices/me/attributes/request/1"
#define TB_TOPIC_RPC_REQUEST        "v1/devices/me/rpc/request/+"
#define TB_TOPIC_RPC_RESPONSE_PFX   "v1/devices/me/rpc/response/"

/* ThingsBoard URLs — BẮT BUỘC định nghĩa qua platformio.ini build_flags
 * -DTHINGSBOARD_BASE_URL=\"http://your-host:9090\"
 * -DMQTT_BROKER_URI=\"mqtt://your-host:1883\"           */
#ifndef THINGSBOARD_BASE_URL
#  error "THINGSBOARD_BASE_URL chưa được định nghĩa! Thêm vào platformio.ini build_flags."
#endif

#ifndef MQTT_BROKER_URI
#  error "MQTT_BROKER_URI chưa được định nghĩa! Thêm vào platformio.ini build_flags."
#endif

/** Khởi tạo MQTT client với token đã có */
void mqtt_app_init(const char *token);

/** Kiểm tra MQTT đã kết nối chưa */
bool mqtt_app_is_connected(void);

/** Publish telemetry message */
void mqtt_app_publish_telemetry(const telemetry_msg_t *telem);

/** Gửi RPC response về ThingsBoard */
void mqtt_app_send_rpc_response(int request_id, bool success, const char *message);

/** MQTT FreeRTOS task function */
void mqtt_task(void *pvParameter);

/** Backward compat */
void mqtt_app_start(const char *token);
