/*
 * camera_task.c — Chụp ảnh định kỳ và đẩy vào frame queue
 *
 * Production mode — không có fake data.
 * Nếu camera không lấy được frame: log lỗi, giảm interval, retrying.
 * Frame mang camera_id để uploader biết gửi vào đúng slot MinIO.
 *
 * Multi-camera: mỗi board chạy 1 firmware instance, g_camera_id
 * được đặt từ ThingsBoard shared attribute "camera_id".
 * Các boards có camera_id khác nhau → MinIO folder khác nhau.
 */
#include "task_manager.h"
#include "esp_camera.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include <string.h>

static const char *TAG = "cam_task";

/* Số lần thất bại liên tiếp trước khi giảm tốc độ chụp */
#define CAM_FAIL_THRESHOLD    3
#define CAM_FAIL_INTERVAL_MS  2000  // Interval khi camera liên tục lỗi

/* Xử lý lệnh đổi cấu hình camera từ MQTT */
static void apply_camera_cmd(const mqtt_cmd_msg_t *cmd)
{
    sensor_t *s = esp_camera_sensor_get();
    if (!s) return;

    switch (cmd->cmd) {
    case MQTT_CMD_CAMERA_RESOLUTION:
        s->set_framesize(s, (framesize_t)cmd->payload.resolution.framesize);
        ESP_LOGI(TAG, "Đổi resolution → %d", cmd->payload.resolution.framesize);
        break;
    case MQTT_CMD_CAMERA_QUALITY:
        s->set_quality(s, cmd->payload.quality.quality);
        ESP_LOGI(TAG, "Đổi JPEG quality → %d", cmd->payload.quality.quality);
        break;
    default:
        break;
    }
}

void camera_task(void *pvParameter)
{
    (void)pvParameter;
    uint32_t seq        = 0;
    int      fail_count = 0;
    TickType_t last_wake = xTaskGetTickCount();

    ESP_LOGI(TAG, "Camera task khởi động (camera_id=%d)", g_camera_id);

    while (g_system_running) {
        /* Kiểm tra lệnh MQTT (resolution/quality — non-blocking) */
        mqtt_cmd_msg_t cmd;
        while (xQueuePeek(g_mqtt_cmd_queue, &cmd, 0) == pdTRUE) {
            if (cmd.cmd == MQTT_CMD_CAMERA_RESOLUTION ||
                cmd.cmd == MQTT_CMD_CAMERA_QUALITY) {
                xQueueReceive(g_mqtt_cmd_queue, &cmd, 0);
                apply_camera_cmd(&cmd);
            } else {
                break; /* Lệnh khác để task khác xử lý */
            }
        }

        /* --- Lấy frame từ camera --- */
        camera_fb_t *fb = esp_camera_fb_get();

        if (!fb) {
            fail_count++;
            g_camera_ok = false;
            ESP_LOGW(TAG, "Không lấy được frame (#%d liên tiếp)", fail_count);

            if (fail_count >= CAM_FAIL_THRESHOLD) {
                /* Camera ngừng hoạt động — chờ lâu hơn, không gửi data rác */
                ESP_LOGE(TAG, "Camera lỗi liên tiếp %d lần — đợi %dms",
                         fail_count, CAM_FAIL_INTERVAL_MS);
                task_manager_report_event("camera_error", "fail_streak");
                vTaskDelay(pdMS_TO_TICKS(CAM_FAIL_INTERVAL_MS));
            } else {
                vTaskDelay(pdMS_TO_TICKS(500));
            }
            last_wake = xTaskGetTickCount(); /* Reset để tránh vTaskDelayUntil overflow */
            continue;
        }

        /* Frame hợp lệ */
        fail_count  = 0;
        g_camera_ok = true;
        g_frame_count++;

        /* Cấp phát bản sao trong PSRAM để gửi vào queue */
        uint8_t *copy = heap_caps_malloc(fb->len, MALLOC_CAP_SPIRAM);
        if (copy) {
            memcpy(copy, fb->buf, fb->len);
            frame_msg_t msg = {
                .data         = copy,
                .len          = fb->len,
                .timestamp_ms = (uint32_t)(xTaskGetTickCount() * portTICK_PERIOD_MS),
                .sequence     = seq++,
                .camera_id    = g_camera_id,  /* Multi-cam: mang ID theo frame */
            };
            if (xQueueSend(g_frame_queue, &msg, 0) != pdTRUE) {
                heap_caps_free(copy);
                ESP_LOGD(TAG, "Frame queue đầy, bỏ frame seq=%lu", (unsigned long)(seq - 1));
            }
        } else {
            ESP_LOGE(TAG, "Không đủ PSRAM cho frame (%u bytes)", (unsigned)fb->len);
        }

        /* Cập nhật latest frame cho HTTP snapshot */
        update_latest_frame_shared(fb->buf, fb->len);

        /* Trả buffer về camera driver */
        esp_camera_fb_return(fb);

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(g_capture_interval_ms));
    }

    ESP_LOGI(TAG, "Camera task kết thúc");
    vTaskDelete(NULL);
}
