#pragma once

#include <stdbool.h>
#include <stdint.h>

/* ============================================================
 * TRAFFIC LIGHT — Chân GPIO (đèn 5V qua relay/transistor)
 * Đổi qua platformio.ini build_flags nếu cần
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

/* ---- Thời gian mỗi pha (ms) — override qua build_flags ---- */
#ifndef TL_RED_DURATION_MS
#error "TL_RED_DURATION_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_YELLOW_DURATION_MS
#error "TL_YELLOW_DURATION_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef TL_GREEN_DURATION_MS
#error "TL_GREEN_DURATION_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif

/* ---- Debounce nút nhấn ------------------------------------ */
#ifndef TL_BUTTON_DEBOUNCE_MS
#error "TL_BUTTON_DEBOUNCE_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif

/* ============================================================
 * Enums
 * ============================================================ */

/** Pha đèn hiện tại */
typedef enum {
    TL_STATE_RED    = 0,
    TL_STATE_YELLOW = 1,
    TL_STATE_GREEN  = 2,
} tl_state_t;

/** Chế độ hoạt động */
typedef enum {
    TL_MODE_NORMAL         = 0,  // Tự động theo chu trình
    TL_MODE_EMERGENCY_RED  = 1,  // Khẩn cấp: khóa đỏ
    TL_MODE_EMERGENCY_GREEN= 2,  // Khẩn cấp: ưu tiên xanh
} tl_mode_t;

/* ============================================================
 * Telemetry snapshot (lấy bởi mqtt_app / health_task)
 * ============================================================ */
typedef struct {
    tl_state_t state;        // Pha đèn hiện tại
    tl_mode_t  mode;         // Chế độ hoạt động
    uint32_t   state_ms;     // Thời gian đã ở pha này (ms)
    uint32_t   phase_duration_ms; // Tổng thời gian pha hiện tại (ms)
    uint32_t   phase_start_ms;    // Thời điểm bắt đầu pha (ms từ boot)
    uint32_t   remain_sec;        // Số giây còn lại của pha hiện tại
    bool       updated;      // true khi vừa có thay đổi mới cần publish
} tl_status_t;

/* ============================================================
 * API
 * ============================================================ */

/** Khởi tạo GPIO, trạng thái ban đầu: ĐỎ, MODE_NORMAL */
void traffic_light_init(void);

/** Đặt pha đèn (áp dụng ngay, publish telemetry) */
void traffic_light_set_state(tl_state_t state);

/** Đặt chế độ hoạt động */
void traffic_light_set_mode(tl_mode_t mode);

/** Đọc kết hợp state + mode */
tl_status_t traffic_light_get_status(void);

/** Xử lý RPC từ ThingsBoard
 *  method: "setNormalMode" | "setEmergencyRed" | "setEmergencyGreen"
 *  @return true nếu method được nhận biết */
bool traffic_light_handle_rpc(const char *method);

/** Cập nhật thời gian pha từ ThingsBoard shared attributes (ms)
 *  Truyền 0 để giữ nguyên giá trị hiện tại */
void traffic_light_set_timings(uint32_t red_ms, uint32_t yellow_ms, uint32_t green_ms);

/** FreeRTOS task function — chạy chu trình + xử lý nút bấm */
void traffic_light_task(void *pvParameter);
