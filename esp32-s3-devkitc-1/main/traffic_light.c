/*
 * traffic_light.c — Đèn giao thông 3 màu + LED 7 đoạn 2 chữ số (đếm ngược).
 *
 * GPIO:  RED=21  YELLOW=47  GREEN=14  (HIGH = sáng, đèn 5V)
 * 7-seg: SDI=38  SCL=39  KLOAD=40
 *        2× 74HC595 nối tiếp, anot chung (LOW = sáng)
 *        shiftOut order: units → tens  (units vào SR2, tens vào SR1)
 *
 * App control hoàn toàn qua MQTT:
 *   setNormalMode | setEmergencyRed | setEmergencyGreen | setTimings
 */
#include "traffic_light.h"
#include "task_manager.h"
#include <string.h>
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "tl";

/* ── LED 7 đoạn — anot chung (mức LOW sáng) ──────────────────────────────── */
static const uint8_t SEG7[10] = {
    0xC0,0xF9,0xA4,0xB0,0x99,0x92,0x82,0xF8,0x80,0x90
};
#define SEG7_BLANK 0xFF

/* ── State ─────────────────────────────────────────────────────────────────── */
static volatile tl_state_t s_state     = TL_STATE_RED;
static volatile tl_mode_t  s_mode      = TL_MODE_NORMAL;
static volatile uint32_t   s_red_ms    = TL_RED_DURATION_MS;
static volatile uint32_t   s_yellow_ms = TL_YELLOW_DURATION_MS;
static volatile uint32_t   s_green_ms  = TL_GREEN_DURATION_MS;
static int64_t  s_phase_start_us       = 0;
static uint8_t  s_last_pub_state       = 0xFF;
static uint8_t  s_last_pub_mode        = 0xFF;
static uint32_t s_last_pub_remain      = UINT32_MAX;

/* ── Helpers ───────────────────────────────────────────────────────────────── */
static inline void pin_set(int pin, int lvl) { if (pin >= 0) gpio_set_level((gpio_num_t)pin, lvl); }

static uint32_t phase_dur_ms(void)
{
    if (s_state == TL_STATE_RED)    return s_red_ms;
    if (s_state == TL_STATE_YELLOW) return s_yellow_ms;
    return s_green_ms;
}

static uint32_t elapsed_ms(void)
{
    int64_t e = esp_timer_get_time() - s_phase_start_us;
    return (e > 0) ? (uint32_t)(e / 1000ULL) : 0;
}

static uint32_t remain_sec(void)
{
    uint32_t dur = phase_dur_ms(), el = elapsed_ms();
    return (dur > el) ? (dur - el + 999U) / 1000U : 0;
}

/* ── 7-segment driver ──────────────────────────────────────────────────────── */
/*
 * Bit-bang shiftOut, MSBFIRST.
 * Khớp với Arduino: shiftOut(SDI, SCL, MSBFIRST, numCode[units]);
 *                   shiftOut(SDI, SCL, MSBFIRST, numCode[tens]);
 * units shift vào trước → đẩy sang SR2 (LED2)
 * tens  shift vào sau   → nằm tại SR1 (LED1)
 */
static void seg_shift_byte(uint8_t b)
{
    for (int i = 7; i >= 0; i--) {
        pin_set(TL_SEG_SDI, (b >> i) & 1);
        pin_set(TL_SEG_SCL, 1);
        pin_set(TL_SEG_SCL, 0);
    }
}

static void seg_write(uint8_t units_code, uint8_t tens_code)
{
    pin_set(TL_SEG_KLOAD, 0);
    seg_shift_byte(units_code);   // units → SR2
    seg_shift_byte(tens_code);    // tens  → SR1
    pin_set(TL_SEG_KLOAD, 1);
}

static void seg_show(uint8_t val)
{
    if (val > 99) val = 99;
    seg_write(SEG7[val % 10], SEG7[val / 10]);
}

static void seg_blank(void) { seg_write(SEG7_BLANK, SEG7_BLANK); }

/* ── Telemetry ─────────────────────────────────────────────────────────────── */
static void publish_if_needed(bool force)
{
    if (!g_telemetry_queue) return;
    uint32_t rs = remain_sec();
    if (!force && (uint8_t)s_state == s_last_pub_state
               && (uint8_t)s_mode  == s_last_pub_mode
               && rs               == s_last_pub_remain) return;

    uint32_t el = elapsed_ms(), dur = phase_dur_ms();
    telemetry_msg_t msg = { .type = TELEMETRY_TRAFFIC_LIGHT };
    msg.data.traffic = (tl_telemetry_t){
        .state            = (uint8_t)s_state,
        .mode             = (uint8_t)s_mode,
        .state_ms         = el,
        .phase_duration_ms = dur,
        .phase_start_ms   = (uint32_t)(s_phase_start_us / 1000ULL),
        .remain_sec       = rs,
        .red_ms           = s_red_ms,
        .yellow_ms        = s_yellow_ms,
        .green_ms         = s_green_ms,
        .red_on    = (s_state == TL_STATE_RED),
        .yellow_on = (s_state == TL_STATE_YELLOW),
        .green_on  = (s_state == TL_STATE_GREEN),
    };
    if (xQueueSend(g_telemetry_queue, &msg, 0) == pdTRUE) {
        s_last_pub_state  = (uint8_t)s_state;
        s_last_pub_mode   = (uint8_t)s_mode;
        s_last_pub_remain = rs;
    }
}

/* ── apply_state ───────────────────────────────────────────────────────────── */
static const char *state_str(tl_state_t s)
{
    if (s == TL_STATE_RED)    return "RED";
    if (s == TL_STATE_YELLOW) return "YELLOW";
    return "GREEN";
}

static void apply_state(tl_state_t state)
{
    pin_set(TL_PIN_RED,    0);
    pin_set(TL_PIN_YELLOW, 0);
    pin_set(TL_PIN_GREEN,  0);
    if (state == TL_STATE_RED)    pin_set(TL_PIN_RED,    1);
    if (state == TL_STATE_YELLOW) pin_set(TL_PIN_YELLOW, 1);
    if (state == TL_STATE_GREEN)  pin_set(TL_PIN_GREEN,  1);
    s_state          = state;
    s_phase_start_us = esp_timer_get_time();
    ESP_LOGI(TAG, "%s mode=%d", state_str(state), (int)s_mode);
    publish_if_needed(true);
}

/* ── Init ──────────────────────────────────────────────────────────────────── */
void traffic_light_init(void)
{
    /* Output pins: đèn + 7-seg */
    const int out_pins[] = { TL_PIN_RED, TL_PIN_YELLOW, TL_PIN_GREEN,
                             TL_SEG_SDI, TL_SEG_SCL, TL_SEG_KLOAD };
    for (int i = 0; i < 6; i++) {
        int p = out_pins[i];
        if (p < 0) continue;
        gpio_config_t c = {
            .pin_bit_mask = 1ULL << p,
            .mode         = GPIO_MODE_OUTPUT,
            .pull_up_en   = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type    = GPIO_INTR_DISABLE,
        };
        if (gpio_config(&c) == ESP_OK) gpio_set_level((gpio_num_t)p, 0);
    }

    seg_blank();
    s_phase_start_us = esp_timer_get_time();
    apply_state(TL_STATE_RED);

    ESP_LOGI(TAG, "init | R=%d Y=%d G=%d | SEG %d/%d/%d | R=%lums Y=%lums G=%lums",
             TL_PIN_RED, TL_PIN_YELLOW, TL_PIN_GREEN,
             TL_SEG_SDI, TL_SEG_SCL, TL_SEG_KLOAD,
             (unsigned long)s_red_ms, (unsigned long)s_yellow_ms, (unsigned long)s_green_ms);
}

/* ── Public API ────────────────────────────────────────────────────────────── */
void traffic_light_set_state(tl_state_t state) { apply_state(state); }

void traffic_light_set_mode(tl_mode_t mode)
{
    s_mode = mode;
    if (mode == TL_MODE_NORMAL) {
        ESP_LOGI(TAG, "mode=NORMAL");
        publish_if_needed(true);
    } else if (mode == TL_MODE_EMERGENCY_RED) {
        apply_state(TL_STATE_RED);
    } else {
        apply_state(TL_STATE_GREEN);
    }
}

tl_status_t traffic_light_get_status(void)
{
    uint32_t el = elapsed_ms(), dur = phase_dur_ms();
    return (tl_status_t){
        .state             = s_state,
        .mode              = s_mode,
        .state_ms          = el,
        .phase_duration_ms = dur,
        .phase_start_ms    = (uint32_t)(s_phase_start_us / 1000ULL),
        .remain_sec        = remain_sec(),
        .updated           = false,
    };
}

bool traffic_light_handle_rpc(const char *method)
{
    if (!method) return false;
    if (!strcmp(method, "setNormalMode"))     { traffic_light_set_mode(TL_MODE_NORMAL);          return true; }
    if (!strcmp(method, "setEmergencyRed"))   { traffic_light_set_mode(TL_MODE_EMERGENCY_RED);   return true; }
    if (!strcmp(method, "setEmergencyGreen")) { traffic_light_set_mode(TL_MODE_EMERGENCY_GREEN); return true; }
    if (!strcmp(method, "getTrafficStatus"))  { return true; }
    return false;
}

void traffic_light_set_timings(uint32_t red_ms, uint32_t yellow_ms, uint32_t green_ms)
{
    if (red_ms)    s_red_ms    = red_ms;
    if (yellow_ms) s_yellow_ms = yellow_ms;
    if (green_ms)  s_green_ms  = green_ms;
    ESP_LOGI(TAG, "timing R=%lums Y=%lums G=%lums",
             (unsigned long)s_red_ms, (unsigned long)s_yellow_ms, (unsigned long)s_green_ms);
    publish_if_needed(true);
}

/* ── FreeRTOS Task ─────────────────────────────────────────────────────────── */
void traffic_light_task(void *pvParameter)
{
    (void)pvParameter;
    bool hold = false;

    while (g_system_running) {
        if (!task_manager_is_system_ready()) {
            if (!hold) {
                hold = true;
                if (s_state != TL_STATE_RED) apply_state(TL_STATE_RED);
                seg_blank();
                ESP_LOGW(TAG, "hold - not ready");
            }
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (hold) {
            hold = false;
            s_phase_start_us = esp_timer_get_time();
            ESP_LOGI(TAG, "resume");
        }

        /* Tự động chuyển pha */
        if (s_mode == TL_MODE_NORMAL) {
            uint32_t el = elapsed_ms();
            if (el >= phase_dur_ms()) {
                if      (s_state == TL_STATE_RED)    apply_state(TL_STATE_GREEN);
                else if (s_state == TL_STATE_GREEN)  apply_state(TL_STATE_YELLOW);
                else                                  apply_state(TL_STATE_RED);
            }
        }

        /* LED 7 đoạn: đếm ngược khi NORMAL, tắt khi khẩn cấp */
        if (s_mode == TL_MODE_NORMAL)
            seg_show((uint8_t)(remain_sec() > 99 ? 99 : remain_sec()));
        else
            seg_blank();

        publish_if_needed(false);
        vTaskDelay(pdMS_TO_TICKS(10));
    }

    pin_set(TL_PIN_RED, 0); pin_set(TL_PIN_YELLOW, 0); pin_set(TL_PIN_GREEN, 0);
    seg_blank();
    vTaskDelete(NULL);
}
