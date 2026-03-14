/*
 * traffic_light.c - Dieu khien den giao thong 3 mau.
 */
#include "traffic_light.h"
#include "task_manager.h"
#include "goouuu_board.h"

#include <string.h>

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "traffic";

static volatile tl_state_t s_state = TL_STATE_RED;
static volatile tl_mode_t  s_mode  = TL_MODE_NORMAL;

static volatile uint32_t s_red_ms    = TL_RED_DURATION_MS;
static volatile uint32_t s_yellow_ms = TL_YELLOW_DURATION_MS;
static volatile uint32_t s_green_ms  = TL_GREEN_DURATION_MS;

static int64_t s_phase_start_us = 0;
static uint8_t s_last_pub_state = 0xFF;
static uint8_t s_last_pub_mode = 0xFF;
static uint32_t s_last_pub_remain_sec = UINT32_MAX;

static bool is_valid_output_pin(int pin)
{
    return pin >= 0 && GPIO_IS_VALID_OUTPUT_GPIO((gpio_num_t)pin);
}

static bool is_valid_input_pin(int pin)
{
    return pin >= 0 && GPIO_IS_VALID_GPIO((gpio_num_t)pin);
}

static bool is_board_reserved_pin(int pin)
{
    if (pin < 0) {
        return false;
    }

    /* ESP32-S3 N16R8 OPI flash/PSRAM chiem tron dai GPIO 26..37. */
    if (pin >= 26 && pin <= 37) {
        return true;
    }

    switch (pin) {
    case GOOUUU_GPIO_BOOT:
    case GOOUUU_GPIO_RST:
    case GOOUUU_GPIO_RGB:
    case GOOUUU_GPIO_TXD:
    case GOOUUU_GPIO_RXD:
    case GOOUUU_I2C_SCL:
    case GOOUUU_I2C_SDA:
    case GOOUUU_TFT_SCK:
    case GOOUUU_TFT_MISO:
    case GOOUUU_TFT_MOSI:
    case GOOUUU_TFT_CS:
    case GOOUUU_TFT_DC:
    case GOOUUU_TOUCH_CS:
    case GOOUUU_TOUCH_DIN:
    case GOOUUU_SD_CMD:
    case GOOUUU_SD_CLK:
    case GOOUUU_SD_DATA:
    case GOOUUU_CAM_XCLK:
    case GOOUUU_CAM_SIOD:
    case GOOUUU_CAM_SIOC:
    case GOOUUU_CAM_VSYNC:
    case GOOUUU_CAM_HREF:
    case GOOUUU_CAM_Y9:
    case GOOUUU_CAM_Y8:
    case GOOUUU_CAM_Y7:
    case GOOUUU_CAM_Y6:
    case GOOUUU_CAM_Y5:
    case GOOUUU_CAM_Y4:
    case GOOUUU_CAM_Y3:
    case GOOUUU_CAM_Y2:
    case GOOUUU_CAM_PCLK:
        return true;
    default:
        return false;
    }
}

static bool is_safe_output_pin(int pin)
{
    return is_valid_output_pin(pin) && !is_board_reserved_pin(pin);
}

static bool is_safe_input_pin(int pin)
{
    return is_valid_input_pin(pin) && !is_board_reserved_pin(pin);
}

static void gpio_write(int pin, int level)
{
    if (is_safe_output_pin(pin)) {
        gpio_set_level((gpio_num_t)pin, level);
    }
}

static uint32_t get_phase_duration_ms(tl_state_t state)
{
    switch (state) {
    case TL_STATE_RED:
        return s_red_ms;
    case TL_STATE_YELLOW:
        return s_yellow_ms;
    case TL_STATE_GREEN:
    default:
        return s_green_ms;
    }
}

static uint32_t get_phase_elapsed_ms(void)
{
    int64_t elapsed_us = esp_timer_get_time() - s_phase_start_us;
    if (elapsed_us <= 0) {
        return 0;
    }
    return (uint32_t)(elapsed_us / 1000ULL);
}

static uint32_t get_phase_remaining_sec(uint32_t elapsed_ms, uint32_t duration_ms)
{
    if (duration_ms <= elapsed_ms) {
        return 0;
    }

    uint32_t remain_ms = duration_ms - elapsed_ms;
    return (remain_ms + 999U) / 1000U;
}

static tl_telemetry_t build_traffic_telemetry_snapshot(void)
{
    uint32_t elapsed_ms = get_phase_elapsed_ms();
    uint32_t duration_ms = get_phase_duration_ms(s_state);

    return (tl_telemetry_t){
        .state = (uint8_t)s_state,
        .mode = (uint8_t)s_mode,
        .state_ms = elapsed_ms,
        .phase_duration_ms = duration_ms,
        .phase_start_ms = (uint32_t)(s_phase_start_us / 1000ULL),
        .remain_sec = get_phase_remaining_sec(elapsed_ms, duration_ms),
        .red_ms = s_red_ms,
        .yellow_ms = s_yellow_ms,
        .green_ms = s_green_ms,
        .red_on = (s_state == TL_STATE_RED),
        .yellow_on = (s_state == TL_STATE_YELLOW),
        .green_on = (s_state == TL_STATE_GREEN),
    };
}

static void publish_current_telemetry_if_needed(bool force)
{
    if (!g_telemetry_queue) {
        return;
    }

    tl_telemetry_t snapshot = build_traffic_telemetry_snapshot();
    if (!force &&
        snapshot.state == s_last_pub_state &&
        snapshot.mode == s_last_pub_mode &&
        snapshot.remain_sec == s_last_pub_remain_sec) {
        return;
    }

    telemetry_msg_t msg = { .type = TELEMETRY_TRAFFIC_LIGHT };
    msg.data.traffic = snapshot;
    if (xQueueSend(g_telemetry_queue, &msg, 0) == pdTRUE) {
        s_last_pub_state = snapshot.state;
        s_last_pub_mode = snapshot.mode;
        s_last_pub_remain_sec = snapshot.remain_sec;
    }
}

static void apply_state(tl_state_t state)
{
    gpio_write(TL_PIN_RED, 0);
    gpio_write(TL_PIN_YELLOW, 0);
    gpio_write(TL_PIN_GREEN, 0);

    switch (state) {
    case TL_STATE_RED:
        gpio_write(TL_PIN_RED, 1);
        ESP_LOGI(TAG, "Traffic light RED (mode=%d)", (int)s_mode);
        break;
    case TL_STATE_YELLOW:
        gpio_write(TL_PIN_YELLOW, 1);
        ESP_LOGI(TAG, "Traffic light YELLOW (mode=%d)", (int)s_mode);
        break;
    case TL_STATE_GREEN:
        gpio_write(TL_PIN_GREEN, 1);
        ESP_LOGI(TAG, "Traffic light GREEN (mode=%d)", (int)s_mode);
        break;
    }

    s_state = state;
    s_phase_start_us = esp_timer_get_time();
    publish_current_telemetry_if_needed(true);
}

void traffic_light_init(void)
{
    const int out_pins[] = { TL_PIN_RED, TL_PIN_YELLOW, TL_PIN_GREEN };
    for (int i = 0; i < 3; i++) {
        const int pin = out_pins[i];
        if (pin < 0) {
            continue;
        }
        if (!is_valid_output_pin(pin)) {
            ESP_LOGW(TAG, "Skip invalid traffic output GPIO %d", pin);
            continue;
        }
        if (is_board_reserved_pin(pin)) {
            ESP_LOGW(TAG, "Skip reserved traffic output GPIO %d on %s", pin, GOOUUU_BOARD_NAME);
            continue;
        }

        gpio_config_t oc = {
            .pin_bit_mask = 1ULL << pin,
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        esp_err_t err = gpio_config(&oc);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Cannot configure traffic output GPIO %d: %s", pin, esp_err_to_name(err));
            continue;
        }

        gpio_set_level((gpio_num_t)pin, 0);
    }

    const int btn_pins[] = { TL_PIN_BTN_RED, TL_PIN_BTN_GREEN };
    for (int i = 0; i < 2; i++) {
        const int pin = btn_pins[i];
        if (pin < 0) {
            continue;
        }
        if (!is_valid_input_pin(pin)) {
            ESP_LOGW(TAG, "Skip invalid traffic button GPIO %d", pin);
            continue;
        }
        if (is_board_reserved_pin(pin)) {
            ESP_LOGW(TAG, "Skip reserved traffic button GPIO %d on %s", pin, GOOUUU_BOARD_NAME);
            continue;
        }

        gpio_config_t ic = {
            .pin_bit_mask = 1ULL << pin,
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        esp_err_t err = gpio_config(&ic);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Cannot configure traffic button GPIO %d: %s", pin, esp_err_to_name(err));
        }
    }

    s_phase_start_us = esp_timer_get_time();
    apply_state(TL_STATE_RED);

    ESP_LOGI(
        TAG,
        "Traffic ready | red=%lums yellow=%lums green=%lums | GPIO R=%d Y=%d G=%d BtnR=%d BtnG=%d",
        (unsigned long)s_red_ms,
        (unsigned long)s_yellow_ms,
        (unsigned long)s_green_ms,
        TL_PIN_RED,
        TL_PIN_YELLOW,
        TL_PIN_GREEN,
        TL_PIN_BTN_RED,
        TL_PIN_BTN_GREEN
    );
}

void traffic_light_set_state(tl_state_t state)
{
    apply_state(state);
}

void traffic_light_set_mode(tl_mode_t mode)
{
    s_mode = mode;
    switch (mode) {
    case TL_MODE_NORMAL:
        ESP_LOGI(TAG, "Traffic mode NORMAL");
        publish_current_telemetry_if_needed(true);
        break;
    case TL_MODE_EMERGENCY_RED:
        apply_state(TL_STATE_RED);
        ESP_LOGI(TAG, "Traffic mode EMERGENCY_RED");
        break;
    case TL_MODE_EMERGENCY_GREEN:
        apply_state(TL_STATE_GREEN);
        ESP_LOGI(TAG, "Traffic mode EMERGENCY_GREEN");
        break;
    }
}

tl_status_t traffic_light_get_status(void)
{
    uint32_t elapsed = get_phase_elapsed_ms();
    uint32_t duration = get_phase_duration_ms(s_state);
    return (tl_status_t){
        .state = s_state,
        .mode = s_mode,
        .state_ms = elapsed,
        .phase_duration_ms = duration,
        .phase_start_ms = (uint32_t)(s_phase_start_us / 1000ULL),
        .remain_sec = get_phase_remaining_sec(elapsed, duration),
        .updated = false,
    };
}

bool traffic_light_handle_rpc(const char *method)
{
    if (!method) {
        return false;
    }
    if (strcmp(method, "setNormalMode") == 0) {
        traffic_light_set_mode(TL_MODE_NORMAL);
        return true;
    }
    if (strcmp(method, "setEmergencyRed") == 0) {
        traffic_light_set_mode(TL_MODE_EMERGENCY_RED);
        return true;
    }
    if (strcmp(method, "setEmergencyGreen") == 0) {
        traffic_light_set_mode(TL_MODE_EMERGENCY_GREEN);
        return true;
    }
    if (strcmp(method, "getTrafficStatus") == 0) {
        return true;
    }
    return false;
}

void traffic_light_set_timings(uint32_t red_ms, uint32_t yellow_ms, uint32_t green_ms)
{
    if (red_ms > 0) {
        s_red_ms = red_ms;
    }
    if (yellow_ms > 0) {
        s_yellow_ms = yellow_ms;
    }
    if (green_ms > 0) {
        s_green_ms = green_ms;
    }
    ESP_LOGI(
        TAG,
        "Traffic timing updated: red=%lums yellow=%lums green=%lums",
        (unsigned long)s_red_ms,
        (unsigned long)s_yellow_ms,
        (unsigned long)s_green_ms
    );
    publish_current_telemetry_if_needed(true);
}

static void check_buttons(void)
{
    static int64_t s_last_btn_us = 0;
    static bool s_btn_red_prev = true;
    static bool s_btn_grn_prev = true;

    const bool has_btn_red = is_safe_input_pin(TL_PIN_BTN_RED);
    const bool has_btn_grn = is_safe_input_pin(TL_PIN_BTN_GREEN);
    if (!has_btn_red && !has_btn_grn) {
        return;
    }

    int64_t now = esp_timer_get_time();
    if ((now - s_last_btn_us) < (int64_t)TL_BUTTON_DEBOUNCE_MS * 1000LL) {
        return;
    }

    bool btn_red = has_btn_red ? (bool)gpio_get_level((gpio_num_t)TL_PIN_BTN_RED) : true;
    bool btn_grn = has_btn_grn ? (bool)gpio_get_level((gpio_num_t)TL_PIN_BTN_GREEN) : true;

    if (has_btn_red && s_btn_red_prev && !btn_red) {
        s_last_btn_us = now;
        tl_mode_t next = (s_mode == TL_MODE_EMERGENCY_RED) ? TL_MODE_NORMAL : TL_MODE_EMERGENCY_RED;
        traffic_light_set_mode(next);
        ESP_LOGI(TAG, "Traffic red button -> mode=%d", (int)next);
    }

    if (has_btn_grn && s_btn_grn_prev && !btn_grn) {
        s_last_btn_us = now;
        tl_mode_t next = (s_mode == TL_MODE_EMERGENCY_GREEN) ? TL_MODE_NORMAL : TL_MODE_EMERGENCY_GREEN;
        traffic_light_set_mode(next);
        ESP_LOGI(TAG, "Traffic green button -> mode=%d", (int)next);
    }

    s_btn_red_prev = btn_red;
    s_btn_grn_prev = btn_grn;
}

static void update_cycle(void)
{
    uint64_t elapsed_ms = (esp_timer_get_time() - s_phase_start_us) / 1000ULL;

    switch (s_state) {
    case TL_STATE_RED:
        if (elapsed_ms >= s_red_ms) {
            apply_state(TL_STATE_GREEN);
        }
        break;
    case TL_STATE_GREEN:
        if (elapsed_ms >= s_green_ms) {
            apply_state(TL_STATE_YELLOW);
        }
        break;
    case TL_STATE_YELLOW:
        if (elapsed_ms >= s_yellow_ms) {
            apply_state(TL_STATE_RED);
        }
        break;
    }
}

void traffic_light_task(void *pvParameter)
{
    (void)pvParameter;
    ESP_LOGI(TAG, "Traffic light task started");

    while (g_system_running) {
        check_buttons();
        if (s_mode == TL_MODE_NORMAL) {
            update_cycle();
        }
        publish_current_telemetry_if_needed(false);
        vTaskDelay(pdMS_TO_TICKS(10));
    }

    gpio_write(TL_PIN_RED, 0);
    gpio_write(TL_PIN_YELLOW, 0);
    gpio_write(TL_PIN_GREEN, 0);

    ESP_LOGI(TAG, "Traffic light task stopped");
    vTaskDelete(NULL);
}
