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

/** Kiểm tra trạng thái MQTT và backend */
bool mqtt_app_is_connected(void);
bool mqtt_app_is_ota_active(void);

/** true khi backend HTTP sync liên tục thất bại (circuit open).
 *  Device vẫn stream và telemetry MQTT bình thường, chỉ backend HTTP fail. */
bool mqtt_app_is_degraded(void);

/** Publish telemetry message */
void mqtt_app_publish_telemetry(const telemetry_msg_t *telem);

/** Gửi RPC response về ThingsBoard */
void mqtt_app_send_rpc_response(int request_id, bool success, const char *message);

/** MQTT FreeRTOS task function */
void mqtt_task(void *pvParameter);

/** Backward compat */
void mqtt_app_start(const char *token);

/**
 * @brief Publish sự kiện "camera đã sync backend" lên Mosquitto.
 * Gọi sau khi backend provision thành công. Backend lắng nghe topic
 * KAI/cameras/{device_name}/status để biết khi nào cần start stream worker.
 * @param camera_id camera_id backend gán về
 * @param is_new    true = thiết bị mới (lần đầu provision), false = reconnect.
 */
void mqtt_app_notify_backend_synced(int camera_id, bool is_new);
