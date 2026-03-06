#pragma once

#include <stdbool.h>

/** Đặt Bearer token xác thực */
void uploader_set_token(const char *token);

/** Đặt địa chỉ backend server và camera_id */
void uploader_set_server(const char *host, int camera_id);

/** Cấu hình MinIO/S3 (truyền NULL để giữ nguyên, "" để xóa)
 *  use_tls: 1=HTTPS, 0=HTTP, -1=giữ nguyên */
void uploader_set_minio_config(const char *endpoint,
                               const char *access_key,
                               const char *secret_key,
                               const char *bucket,
                               const char *region,
                               int use_tls);

/** FreeRTOS task function */
void uploader_task(void *pvParameter);
