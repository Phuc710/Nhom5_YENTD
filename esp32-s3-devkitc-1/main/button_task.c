/*
 * button_task.c — Xử lý nút bấm BOOT (GPIO 0)
 *
 * HOLD > 3 giây → Factory Reset:
 *    - LED nhấp nháy đỏ liên tục trong khi giữ
 *    - Sau 3s đủ: nháy nhanh 5 lần → xóa TOÀN BỘ NVS
 *    - Khởi động lại → thiết bị về trạng thái trống như mới
 *
 * Nhấn nhanh → bỏ qua
 */
#include "task_manager.h"
#include "app_config.h"
#include "goouuu_board.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"

static const char *TAG = "btn";

#define FACTORY_HOLD_MS 3000   /* Giữ đủ 3 giây để kích hoạt factory reset */
#define DEBOUNCE_MS     50     /* Debounce nút bấm */
#define BLINK_PERIOD_MS 250    /* Chu kỳ nhấp nháy LED khi đang giữ nút */

void button_task(void *pvParameter)
{
    (void)pvParameter;

    /* Cấu hình GPIO nút BOOT — input, pull-up nội */
    gpio_config_t io_cfg = {
        .pin_bit_mask = (1ULL << GOOUUU_GPIO_BOOT),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_cfg);

    ESP_LOGI(TAG, "🔘 Boot Button: Đang chạy (GPIO %d) — Giữ %d giây để RESET",
             GOOUUU_GPIO_BOOT, FACTORY_HOLD_MS / 1000);

    bool     btn_prev     = true;  /* HIGH = không nhấn (pull-up active) */
    uint32_t press_start  = 0;
    bool     long_handled = false;
    bool     blink_state  = false;
    uint32_t last_blink   = 0;

    while (g_system_running) {
        vTaskDelay(pdMS_TO_TICKS(DEBOUNCE_MS));
        bool btn_cur = (bool)gpio_get_level(GOOUUU_GPIO_BOOT);
        uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;

        /* Phát hiện cạnh xuống (nhấn nút) */
        if (!btn_cur && btn_prev) {
            press_start  = now;
            long_handled = false;
            blink_state  = false;
            last_blink   = now;
        }

        /* Đang giữ nút — xử lý nhấp nháy LED và kiểm tra ngưỡng 3s */
        if (!btn_cur && !long_handled) {
            uint32_t held_ms = now - press_start;

            /* Nhấp nháy đỏ mỗi 250ms khi đang giữ — feedback real-time cho user */
            if (now - last_blink >= BLINK_PERIOD_MS) {
                last_blink = now;
                blink_state = !blink_state;
                ESP_LOGD(TAG, "Holding... blink=%d", blink_state);
            }

            /* Đủ 3 giây → thực hiện factory reset */
            if (held_ms >= FACTORY_HOLD_MS) {
                long_handled = true;
                ESP_LOGW(TAG, "⚠️ Factory Reset: Đã giữ đủ %lums!", (unsigned long)held_ms);
                ESP_LOGW(TAG, "⚠️ Factory Reset: Đang xóa cấu hình WiFi và Token...");

                /* Nháy nhanh 5 lần đỏ xác nhận reset bắt đầu */
                for (int i = 0; i < 5; i++) {
                    ESP_LOGI(TAG, "Factory reset blink %d/5", i + 1);
                    vTaskDelay(pdMS_TO_TICKS(160));
                }

                /* Xóa TOÀN BỘ NVS partition */
                esp_err_t err = app_config_clear();
                if (err == ESP_OK) {
                    ESP_LOGI(TAG, "✅ Factory Reset: Hoàn tất! Thiết bị đã được làm sạch");
                } else {
                    ESP_LOGE(TAG, "❌ Factory Reset: Thất bại (%s)", esp_err_to_name(err));
                }

                vTaskDelay(pdMS_TO_TICKS(300));
                esp_restart();
            }
        }

        /* Nhả nút trước 3s → khôi phục LED về trạng thái trước */
        if (btn_cur && !btn_prev && !long_handled) {
            uint32_t held_ms = now - press_start;
            if (held_ms > 100) {
                ESP_LOGD(TAG, "🔘 Boot Button: Nút nhả sau %lu ms (chưa đủ %d ms để reset)",
                         (unsigned long)held_ms, FACTORY_HOLD_MS);
            }
            /* Khôi phục về trạng thái bình thường */
            ESP_LOGD(TAG, "🔘 Boot Button: Nhả sới, tiếp tục chạy bình thường");
        }

        btn_prev = btn_cur;
    }

    ESP_LOGI(TAG, "🔘 Boot Button: Đã kết thúc");
    vTaskDelete(NULL);
}
