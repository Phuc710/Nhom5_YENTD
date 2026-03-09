/*
 * button_task.c — Xử lý nút bấm BOOT (GPIO 0)
 *
 * Giữ nút > 3 giây → factory reset (xóa config NVS + reboot)
 * Nhấn nhanh       → không làm gì (dành cho debug)
 */
#include "task_manager.h"
#include "app_config.h"
#include "led_status.h"
#include "goouuu_board.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"

static const char *TAG = "btn_task";

#define FACTORY_HOLD_MS  3000   // Giữ 3 giây để factory reset
#define DEBOUNCE_MS      50     // Debounce button

void button_task(void *pvParameter)
{
    (void)pvParameter;

    /* Cấu hình GPIO nút BOOT */
    gpio_config_t io_cfg = {
        .pin_bit_mask = (1ULL << GOOUUU_GPIO_BOOT),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_cfg);

    ESP_LOGI(TAG, "Task nút bấm khởi động (GPIO %d)", GOOUUU_GPIO_BOOT);

    bool     btn_prev     = true;  // HIGH = không nhấn (pull-up)
    uint32_t press_start  = 0;
    bool     long_handled = false;

    while (g_system_running) {
        vTaskDelay(pdMS_TO_TICKS(DEBOUNCE_MS));

        bool btn_cur = gpio_get_level(GOOUUU_GPIO_BOOT);

        if (!btn_cur && btn_prev) {
            /* Phát hiện nút nhấn (falling edge) */
            press_start  = xTaskGetTickCount();
            long_handled = false;
        }

        if (!btn_cur && !long_handled) {
            uint32_t held_ms = (xTaskGetTickCount() - press_start) * portTICK_PERIOD_MS;

            if (held_ms >= FACTORY_HOLD_MS) {
                long_handled = true;
                ESP_LOGW(TAG, "Giữ nút %lu ms -> Factory Reset!", (unsigned long)held_ms);

                /* Nháy đỏ 3 lần để báo hiệu */
                for (int i = 0; i < 3; i++) {
                    led_status_set_rgb(64, 0, 0);
                    vTaskDelay(pdMS_TO_TICKS(150));
                    led_status_off();
                    vTaskDelay(pdMS_TO_TICKS(150));
                }

                app_config_clear();
                vTaskDelay(pdMS_TO_TICKS(500));
                esp_restart();
            }
        }

        if (btn_cur && !btn_prev && !long_handled) {
            uint32_t held_ms = (xTaskGetTickCount() - press_start) * portTICK_PERIOD_MS;
            ESP_LOGI(TAG, "Nút nhả sau %lu ms", (unsigned long)held_ms);
        }

        btn_prev = btn_cur;
    }

    ESP_LOGI(TAG, "Task nút bấm kết thúc");
    vTaskDelete(NULL);
}
