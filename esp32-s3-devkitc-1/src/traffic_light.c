/*
 * traffic_light.c — Điều khiển đèn giao thông 3 màu (5V qua relay/transistor)
 *
 * Tính năng:
 *   - Chu trình tự động: ĐỎ → XANH → VÀNG → ĐỎ
 *   - 2 nút bấm vật lý (toggle khẩn cấp đỏ / xanh)
 *   - Điều khiển từ ThingsBoard qua MQTT RPC
 *   - Telemetry: traffic_light_state, operation_mode, state_ms
 *   - Thời gian mỗi pha có thể đổi real-time từ ThingsBoard
 */
#include "traffic_light.h"
#include "task_manager.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "traffic";

/* ---- Trạng thái nội bộ ---- */
static volatile tl_state_t  s_state = TL_STATE_RED;
static volatile tl_mode_t   s_mode  = TL_MODE_NORMAL;

static volatile uint32_t s_red_ms    = TL_RED_DURATION_MS;
static volatile uint32_t s_yellow_ms = TL_YELLOW_DURATION_MS;
static volatile uint32_t s_green_ms  = TL_GREEN_DURATION_MS;

static int64_t s_phase_start_us = 0;

/* ============================================================
 * Private helpers
 * ============================================================ */

static void gpio_write(int pin, int level)
{
    if (pin >= 0) gpio_set_level((gpio_num_t)pin, level);
}

static void publish_tl_telemetry(tl_state_t st, tl_mode_t mode)
{
    if (!g_telemetry_queue) return;

    uint32_t elapsed = (uint32_t)((esp_timer_get_time() - s_phase_start_us) / 1000LL);
    telemetry_msg_t msg = { .type = TELEMETRY_TRAFFIC_LIGHT };
    msg.data.traffic.state    = (uint8_t)st;
    msg.data.traffic.mode     = (uint8_t)mode;
    msg.data.traffic.state_ms = elapsed;
    xQueueSend(g_telemetry_queue, &msg, 0);
}

static void apply_state(tl_state_t state)
{
    /* Tắt tất cả trước */
    gpio_write(TL_PIN_RED,    0);
    gpio_write(TL_PIN_YELLOW, 0);
    gpio_write(TL_PIN_GREEN,  0);

    switch (state) {
    case TL_STATE_RED:
        gpio_write(TL_PIN_RED, 1);
        ESP_LOGI(TAG, "🔴 ĐỎ (mode=%d)", (int)s_mode);
        break;
    case TL_STATE_YELLOW:
        gpio_write(TL_PIN_YELLOW, 1);
        ESP_LOGI(TAG, "🟡 VÀNG (mode=%d)", (int)s_mode);
        break;
    case TL_STATE_GREEN:
        gpio_write(TL_PIN_GREEN, 1);
        ESP_LOGI(TAG, "🟢 XANH (mode=%d)", (int)s_mode);
        break;
    }

    s_state          = state;
    s_phase_start_us = esp_timer_get_time();

    publish_tl_telemetry(state, s_mode);
}

/* ============================================================
 * Init
 * ============================================================ */

void traffic_light_init(void)
{
    /* Chân đèn OUTPUT */
    const int out_pins[] = { TL_PIN_RED, TL_PIN_YELLOW, TL_PIN_GREEN };
    for (int i = 0; i < 3; i++) {
        if (out_pins[i] < 0) continue;
        gpio_config_t oc = {
            .pin_bit_mask = 1ULL << out_pins[i],
            .mode         = GPIO_MODE_OUTPUT,
        };
        gpio_config(&oc);
        gpio_set_level((gpio_num_t)out_pins[i], 0);
    }

    /* Chân nút INPUT_PULLUP */
    const int btn_pins[] = { TL_PIN_BTN_RED, TL_PIN_BTN_GREEN };
    for (int i = 0; i < 2; i++) {
        if (btn_pins[i] < 0) continue;
        gpio_config_t ic = {
            .pin_bit_mask = 1ULL << btn_pins[i],
            .mode         = GPIO_MODE_INPUT,
            .pull_up_en   = GPIO_PULLUP_ENABLE,
        };
        gpio_config(&ic);
    }

    s_phase_start_us = esp_timer_get_time();
    apply_state(TL_STATE_RED);

    ESP_LOGI(TAG, "Đèn giao thông OK | R=%lums Y=%lums G=%lums | "
             "GPIO R=%d Y=%d G=%d BtnR=%d BtnG=%d",
             (unsigned long)s_red_ms,
             (unsigned long)s_yellow_ms,
             (unsigned long)s_green_ms,
             TL_PIN_RED, TL_PIN_YELLOW, TL_PIN_GREEN,
             TL_PIN_BTN_RED, TL_PIN_BTN_GREEN);
}

/* ============================================================
 * Public API
 * ============================================================ */

void traffic_light_set_state(tl_state_t state)
{
    apply_state(state);
}

void traffic_light_set_mode(tl_mode_t mode)
{
    s_mode = mode;
    switch (mode) {
    case TL_MODE_NORMAL:
        ESP_LOGI(TAG, "Chế độ: BÌNH THƯỜNG");
        break;
    case TL_MODE_EMERGENCY_RED:
        apply_state(TL_STATE_RED);
        ESP_LOGI(TAG, "Chế độ: KHẨN CẤP ĐỎ");
        break;
    case TL_MODE_EMERGENCY_GREEN:
        apply_state(TL_STATE_GREEN);
        ESP_LOGI(TAG, "Chế độ: KHẨN CẤP XANH");
        break;
    }
}

tl_status_t traffic_light_get_status(void)
{
    uint32_t elapsed = (uint32_t)((esp_timer_get_time() - s_phase_start_us) / 1000LL);
    return (tl_status_t){
        .state    = s_state,
        .mode     = s_mode,
        .state_ms = elapsed,
    };
}

bool traffic_light_handle_rpc(const char *method)
{
    if (!method) return false;
    if (strcmp(method, "setNormalMode")     == 0) { traffic_light_set_mode(TL_MODE_NORMAL);          return true; }
    if (strcmp(method, "setEmergencyRed")   == 0) { traffic_light_set_mode(TL_MODE_EMERGENCY_RED);   return true; }
    if (strcmp(method, "setEmergencyGreen") == 0) { traffic_light_set_mode(TL_MODE_EMERGENCY_GREEN); return true; }
    if (strcmp(method, "getTrafficStatus")  == 0) return true;
    return false;
}

void traffic_light_set_timings(uint32_t red_ms, uint32_t yellow_ms, uint32_t green_ms)
{
    if (red_ms    > 0) s_red_ms    = red_ms;
    if (yellow_ms > 0) s_yellow_ms = yellow_ms;
    if (green_ms  > 0) s_green_ms  = green_ms;
    ESP_LOGI(TAG, "Timing: R=%lums Y=%lums G=%lums",
             (unsigned long)s_red_ms,
             (unsigned long)s_yellow_ms,
             (unsigned long)s_green_ms);
}

/* ============================================================
 * FreeRTOS Task — chu trình + nút bấm
 * ============================================================ */

static void check_buttons(void)
{
    static int64_t s_last_btn_us  = 0;
    static bool    s_btn_red_prev = true;
    static bool    s_btn_grn_prev = true;

    int64_t now = esp_timer_get_time();
    if ((now - s_last_btn_us) < (int64_t)TL_BUTTON_DEBOUNCE_MS * 1000LL) return;

    bool btn_red = (bool)gpio_get_level((gpio_num_t)TL_PIN_BTN_RED);
    bool btn_grn = (bool)gpio_get_level((gpio_num_t)TL_PIN_BTN_GREEN);

    /* Falling edge = nút nhấn (pull-up → LOW) */
    if (s_btn_red_prev && !btn_red) {
        s_last_btn_us = now;
        tl_mode_t next = (s_mode == TL_MODE_EMERGENCY_RED)
                         ? TL_MODE_NORMAL : TL_MODE_EMERGENCY_RED;
        traffic_light_set_mode(next);
        ESP_LOGI(TAG, "Nút ĐỎ → mode=%d", (int)next);
    }

    if (s_btn_grn_prev && !btn_grn) {
        s_last_btn_us = now;
        tl_mode_t next = (s_mode == TL_MODE_EMERGENCY_GREEN)
                         ? TL_MODE_NORMAL : TL_MODE_EMERGENCY_GREEN;
        traffic_light_set_mode(next);
        ESP_LOGI(TAG, "Nút XANH → mode=%d", (int)next);
    }

    s_btn_red_prev = btn_red;
    s_btn_grn_prev = btn_grn;
}

static void update_cycle(void)
{
    uint64_t elapsed_ms = (esp_timer_get_time() - s_phase_start_us) / 1000ULL;

    switch (s_state) {
    case TL_STATE_RED:
        if (elapsed_ms >= s_red_ms)    apply_state(TL_STATE_GREEN);
        break;
    case TL_STATE_GREEN:
        if (elapsed_ms >= s_green_ms)  apply_state(TL_STATE_YELLOW);
        break;
    case TL_STATE_YELLOW:
        if (elapsed_ms >= s_yellow_ms) apply_state(TL_STATE_RED);
        break;
    }
}

void traffic_light_task(void *pvParameter)
{
    (void)pvParameter;
    ESP_LOGI(TAG, "Traffic light task khởi động");

    while (g_system_running) {
        check_buttons();
        if (s_mode == TL_MODE_NORMAL) {
            update_cycle();
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }

    /* Tắt đèn khi hệ thống dừng */
    gpio_write(TL_PIN_RED,    0);
    gpio_write(TL_PIN_YELLOW, 0);
    gpio_write(TL_PIN_GREEN,  0);

    ESP_LOGI(TAG, "Traffic light task kết thúc");
    vTaskDelete(NULL);
}
