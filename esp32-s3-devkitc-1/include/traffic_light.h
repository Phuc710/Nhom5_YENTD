#pragma once

#include <stdbool.h>
#include <stdint.h>

/* ============================================================
 * GPIO — đèn giao thông 5V (qua transistor/relay)
 * Set trong platformio.ini [device_defaults]
 * ============================================================ */
#ifndef TL_PIN_RED
#error "TL_PIN_RED chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_PIN_YELLOW
#error "TL_PIN_YELLOW chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_PIN_GREEN
#error "TL_PIN_GREEN chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_PIN_BTN_RED
#error "TL_PIN_BTN_RED chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_PIN_BTN_GREEN
#error "TL_PIN_BTN_GREEN chua duoc dinh nghia. Dat trong platformio.ini."
#endif

/* ============================================================
 * GPIO — LED 7 đoạn 2 chữ số (Shift Register 74HC595 x2)
 * SDI=38, SCL=39, KLOAD=40
 * ============================================================ */
#ifndef TL_SEG_SDI
#error "TL_SEG_SDI chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_SEG_SCL
#error "TL_SEG_SCL chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_SEG_KLOAD
#error "TL_SEG_KLOAD chua duoc dinh nghia. Dat trong platformio.ini."
#endif

/* ---- Thời gian mỗi pha (ms) -------------------------------- */
#ifndef TL_RED_DURATION_MS
#error "TL_RED_DURATION_MS chua duoc dinh nghia."
#endif
#ifndef TL_YELLOW_DURATION_MS
#error "TL_YELLOW_DURATION_MS chua duoc dinh nghia."
#endif
#ifndef TL_GREEN_DURATION_MS
#error "TL_GREEN_DURATION_MS chua duoc dinh nghia."
#endif

#ifndef TL_BUTTON_DEBOUNCE_MS
#error "TL_BUTTON_DEBOUNCE_MS chua duoc dinh nghia."
#endif

/* ============================================================
 * Enums
 * ============================================================ */
typedef enum {
    TL_STATE_RED    = 0,
    TL_STATE_YELLOW = 1,
    TL_STATE_GREEN  = 2,
} tl_state_t;

typedef enum {
    TL_MODE_NORMAL          = 0,
    TL_MODE_EMERGENCY_RED   = 1,
    TL_MODE_EMERGENCY_GREEN = 2,
} tl_mode_t;

/* ============================================================
 * Telemetry snapshot
 * ============================================================ */
typedef struct {
    tl_state_t state;
    tl_mode_t  mode;
    uint32_t   state_ms;
    uint32_t   phase_duration_ms;
    uint32_t   phase_start_ms;
    uint32_t   remain_sec;
    bool       updated;
} tl_status_t;

/* ============================================================
 * API
 * ============================================================ */
void        traffic_light_init(void);
void        traffic_light_set_state(tl_state_t state);
void        traffic_light_set_mode(tl_mode_t mode);
tl_status_t traffic_light_get_status(void);
bool        traffic_light_handle_rpc(const char *method);
void        traffic_light_set_timings(uint32_t red_ms, uint32_t yellow_ms, uint32_t green_ms);
void        traffic_light_task(void *pvParameter);
