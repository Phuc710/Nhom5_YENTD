/*
 * backend_sync.h — Đồng bộ ESP32 với backend HTTP (provision + heartbeat).
 *
 * Module này tách biệt hoàn toàn HTTP data-plane khỏi MQTT control-plane.
 * Backend sync chạy trong FreeRTOS task riêng, không block MQTT task.
 *
 * Circuit breaker:
 *   - Sau BACKEND_SYNC_MAX_ATTEMPTS lần provision fail liên tiếp → degrade mode
 *   - Degrade mode: retry interval tăng lên BACKEND_SYNC_DEGRADE_INTERVAL_MS
 *   - Heartbeat 404 → tự động reset về provision phase
 *   - Degrade mode được reset ngay khi backend trả lại 2xx
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "task_common.h"
#include "app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Timing defaults (có thể override từ platformio.ini) ---- */
#ifndef BACKEND_SYNC_RETRY_MS
#define BACKEND_SYNC_RETRY_MS            5000
#endif
#ifndef BACKEND_HEARTBEAT_INTERVAL_MS
#define BACKEND_HEARTBEAT_INTERVAL_MS    5000
#endif
#ifndef BACKEND_HEARTBEAT_TIMEOUT_MS
#define BACKEND_HEARTBEAT_TIMEOUT_MS     15000
#endif
#ifndef BACKEND_PROVISION_TIMEOUT_MS
#define BACKEND_PROVISION_TIMEOUT_MS     20000
#endif
#ifndef BACKEND_SYNC_DEGRADE_INTERVAL_MS
/* Khi circuit open, retry provision giãn ra 60s để không spam backend */
#define BACKEND_SYNC_DEGRADE_INTERVAL_MS 60000
#endif

/* ---- Public API ---- */

/**
 * @brief Khởi động backend sync task.
 *
 * Phải gọi SAU khi WiFi đã có IP và token đã sẵn sàng.
 * Idempotent: gọi nhiều lần không tạo thêm task.
 *
 * @param cfg    Pointer đến app_config đã load (chứa token, camera_id...).
 * @param token  ThingsBoard access token (có thể NULL nếu chưa có).
 */
void backend_sync_start(const app_config_t *cfg, const char *token);

/**
 * @brief Cập nhật token sau khi provision ThingsBoard thành công.
 * Thread-safe, có thể gọi từ mqtt_task.
 */
void backend_sync_set_token(const char *token);

/**
 * @brief Cập nhật toàn bộ config (camera_id, device_name, location...).
 * Gọi khi app_config thay đổi runtime.
 */
void backend_sync_update_config(const app_config_t *cfg);

/**
 * @brief Kích hoạt sync ngay (notify task).
 * An toàn để gọi từ MQTT event handler.
 */
void backend_sync_notify(void);

/**
 * @brief Báo hiệu backend_synced = 0 để force re-provision.
 * Dùng khi MQTT reconnect sau khi token bị xóa.
 */
void backend_sync_force_reprovision(void);

/**
 * @brief Push health snapshot để heartbeat thread dùng (thread-safe).
 */
void backend_sync_push_health(const health_telemetry_t *health);

/**
 * @brief Dừng backend sync task (system shutdown).
 */
void backend_sync_stop(void);

/* ---- State query (thread-safe) ---- */

/** true khi circuit breaker open (provision fail > MAX_ATTEMPTS lần) */
bool backend_sync_is_degraded(void);

/** Chuỗi trạng thái đồng bộ để publish MQTT attribute. Không allocate memory. */
const char *backend_sync_get_state_str(void);

/**
 * @brief Trả về camera_id mà backend gán về sau khi provision.
 * @return camera_id (> 0) nếu đã sync thành công, -1 nếu chưa.
 * Không cần mutex — chỉ write 1 lần từ backend_sync task context.
 */
int backend_sync_get_assigned_camera_id(void);

#ifdef __cplusplus
}
#endif
