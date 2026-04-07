/*
 * camera_task.c - Capture frames periodically and apply camera commands.
 */
#include "task_manager.h"
#include "traffic_light.h"

#include <string.h>

#include "esp_camera.h"
#include "esp_log.h"
#include "goouuu_camera.h"

static const char *TAG = "cam_task";

#define CAM_FAIL_THRESHOLD   3
#define CAM_FAIL_INTERVAL_MS 2000

static void apply_camera_cmd(const mqtt_cmd_msg_t *cmd)
{
    sensor_t *sensor = esp_camera_sensor_get();
    if (!cmd) {
        return;
    }

    switch (cmd->cmd) {
    case MQTT_CMD_CAMERA_RESOLUTION:
        if (!sensor || sensor->status.framesize == cmd->payload.resolution.framesize) {
            return;
        }
        sensor->set_framesize(sensor, (framesize_t)cmd->payload.resolution.framesize);
        ESP_LOGI(TAG, "Doi resolution -> %d", cmd->payload.resolution.framesize);
        break;

    case MQTT_CMD_CAMERA_QUALITY:
        if (!sensor || sensor->status.quality == cmd->payload.quality.quality) {
            return;
        }
        sensor->set_quality(sensor, cmd->payload.quality.quality);
        ESP_LOGI(TAG, "Doi JPEG quality -> %d", cmd->payload.quality.quality);
        break;

    case MQTT_CMD_CAPTURE_INTERVAL:
        if (g_capture_interval_ms == (uint32_t)cmd->payload.interval.interval_ms) {
            return;
        }
        g_capture_interval_ms = (uint32_t)cmd->payload.interval.interval_ms;
        ESP_LOGI(TAG, "Doi capture_interval_ms -> %lu", (unsigned long)g_capture_interval_ms);
        break;

    default:
        break;
    }
}

void camera_task(void *pvParameter)
{
    (void)pvParameter;

    int fail_count = 0;
    bool recovery_attempted = false;
    TickType_t last_wake = xTaskGetTickCount();

    ESP_LOGI(TAG, "Task Camera khoi dong [ID:%d]", g_camera_id);

    while (g_system_running) {
        mqtt_cmd_msg_t cmd;
        while (xQueuePeek(g_mqtt_cmd_queue, &cmd, 0) == pdTRUE) {
            if (cmd.cmd == MQTT_CMD_CAMERA_RESOLUTION ||
                cmd.cmd == MQTT_CMD_CAMERA_QUALITY ||
                cmd.cmd == MQTT_CMD_CAPTURE_INTERVAL) {
                xQueueReceive(g_mqtt_cmd_queue, &cmd, 0);
                apply_camera_cmd(&cmd);
            } else {
                break;
            }
        }

        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) {
            fail_count++;
            g_camera_ok = false;
            ESP_LOGW(TAG, "Khong lay duoc frame (#%d)", fail_count);

            if (fail_count >= CAM_FAIL_THRESHOLD) {
                if (!recovery_attempted && !goouuu_camera_safe_mode_active()) {
                    ESP_LOGW(TAG, "Camera fail streak -> kich hoat safe mode recovery");
                    task_manager_report_event("camera_error", "safe_mode_recovery");
                    if (goouuu_camera_recover_safe_mode() == ESP_OK) {
                        recovery_attempted = true;
                        fail_count = 0;
                        vTaskDelay(pdMS_TO_TICKS(750));
                    } else {
                        ESP_LOGE(TAG, "Safe mode recovery that bai, thu lai sau %dms",
                                 CAM_FAIL_INTERVAL_MS);
                        task_manager_report_event("camera_error", "safe_mode_recovery_failed");
                        vTaskDelay(pdMS_TO_TICKS(CAM_FAIL_INTERVAL_MS));
                    }
                } else {
                    ESP_LOGE(TAG, "Camera loi lien tiep %d lan, thu lai sau %dms",
                             fail_count, CAM_FAIL_INTERVAL_MS);
                    task_manager_report_event("camera_error", "fail_streak");
                    vTaskDelay(pdMS_TO_TICKS(CAM_FAIL_INTERVAL_MS));
                }
            } else {
                vTaskDelay(pdMS_TO_TICKS(500));
            }

            last_wake = xTaskGetTickCount();
            continue;
        }

        fail_count = 0;
        recovery_attempted = recovery_attempted || goouuu_camera_safe_mode_active();
        g_camera_ok = true;
        update_latest_frame_shared(fb->buf, fb->len);
        g_frame_count++;
        esp_camera_fb_return(fb);

        /* Cap toc do streaming de tranh FB-OVF.
         * VGA@q12 ~25KB/frame. WiFi ESP32 ~1.2MB/s thuc te.
         * 15fps * 25KB = 375KB/s — an toan, du nhanh cho AI detect. */
        if (g_stream_client_count > 0) {
            /* Dang stream: gioi han ~15fps de WiFi kip gui */
            vTaskDelay(pdMS_TO_TICKS(66));
            last_wake = xTaskGetTickCount();
        } else if (g_capture_interval_ms == 0) {
            /* Khong co client, khong co interval: yield nhe */
            last_wake = xTaskGetTickCount();
            taskYIELD();
        } else {
            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(g_capture_interval_ms));
        }
    }

    ESP_LOGI(TAG, "Task Camera ket thuc");
    vTaskDelete(NULL);
}
