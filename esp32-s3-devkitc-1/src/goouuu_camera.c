/*
 * goouuu_camera.c — Cấu hình camera GOOUUU Tech ESP32-S3-CAM N16R8
 *
 * Mặc định: VGA 640×480, JPEG quality=10, fb=2 (PSRAM), GRAB_LATEST
 */
#include "goouuu_camera.h"
#include "goouuu_board.h"
#include "esp_log.h"
#include "esp_heap_caps.h"

static const char *TAG = "goouuu_cam";

camera_config_t goouuu_camera_config_default(void)
{
    /* Phát hiện PSRAM */
    size_t psram_size = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    bool   has_psram  = (psram_size >= GOOUUU_CAM_MIN_PSRAM_BYTES);

    camera_config_t cfg = {
        /* ---- Chân GPIO (từ sơ đồ chân GOOUUU N16R8) ---- */
        .pin_pwdn    = CAM_PIN_PWDN,
        .pin_reset   = CAM_PIN_RESET,
        .pin_xclk    = CAM_PIN_XCLK,
        .pin_sccb_sda= CAM_PIN_SIOD,
        .pin_sccb_scl= CAM_PIN_SIOC,
        .pin_d7      = CAM_PIN_D7,
        .pin_d6      = CAM_PIN_D6,
        .pin_d5      = CAM_PIN_D5,
        .pin_d4      = CAM_PIN_D4,
        .pin_d3      = CAM_PIN_D3,
        .pin_d2      = CAM_PIN_D2,
        .pin_d1      = CAM_PIN_D1,
        .pin_d0      = CAM_PIN_D0,
        .pin_vsync   = CAM_PIN_VSYNC,
        .pin_href    = CAM_PIN_HREF,
        .pin_pclk    = CAM_PIN_PCLK,

        /* ---- Clock ---- */
        .xclk_freq_hz = 20000000,
        .ledc_timer   = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,

        /* ---- Ảnh ---- */
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size   = FRAMESIZE_VGA,   // 640×480 — nhận diện biển số tốt
        .jpeg_quality = 10,              // 10 = chất lượng tốt, file nhỏ vừa
        .fb_count     = 2,               // double buffer — camera chạy mượt
        .grab_mode    = CAMERA_GRAB_LATEST,  // luôn lấy frame mới nhất
        .fb_location  = has_psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM,
    };

    if (has_psram) {
        ESP_LOGI(TAG, "Camera: VGA JPEG q=10 fb=2 PSRAM (%.1f MB)",
                 psram_size / 1048576.0f);
    } else {
        ESP_LOGW(TAG, "Camera: VGA JPEG q=10 fb=1 DRAM (không có PSRAM)");
        cfg.fb_count = 1; /* Giảm xuống 1 nếu không có PSRAM */
    }

    return cfg;
}
