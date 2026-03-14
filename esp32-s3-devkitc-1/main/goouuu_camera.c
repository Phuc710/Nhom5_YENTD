/*
 * goouuu_camera.c — Cấu hình camera GOOUUU Tech ESP32-S3-CAM N16R8
 *
 * Mặc định: VGA 640×480, JPEG quality=10, fb=2 (PSRAM), GRAB_LATEST
 */
#include "goouuu_camera.h"
#include "goouuu_board.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include <ctype.h>
#include <string.h>

static const char *TAG = "goouuu_cam";

typedef struct {
    const char *name;
    framesize_t framesize;
} framesize_name_t;

static const framesize_name_t s_framesizes[] = {
    { "QQVGA", FRAMESIZE_QQVGA },
    { "HQVGA", FRAMESIZE_HQVGA },
    { "QVGA",  FRAMESIZE_QVGA  },
    { "CIF",   FRAMESIZE_CIF   },
    { "VGA",   FRAMESIZE_VGA   },
    { "SVGA",  FRAMESIZE_SVGA  },
    { "XGA",   FRAMESIZE_XGA   },
    { "HD",    FRAMESIZE_HD    },
    { "SXGA",  FRAMESIZE_SXGA  },
    { "UXGA",  FRAMESIZE_UXGA  },
};

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
        .xclk_freq_hz = GOOUUU_CAM_XCLK_HZ,
        .ledc_timer   = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,

        /* ---- Ảnh ---- */
        .pixel_format = GOOUUU_CAM_PIXEL_FORMAT,
        .frame_size   = has_psram ? GOOUUU_CAM_FRAME_SIZE_PSRAM : GOOUUU_CAM_FRAME_SIZE_NO_PSRAM,
        .jpeg_quality = has_psram ? GOOUUU_CAM_JPEG_QUALITY_PSRAM : GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM,
        .fb_count     = has_psram ? GOOUUU_CAM_FB_COUNT_PSRAM : GOOUUU_CAM_FB_COUNT_NO_PSRAM,
        .grab_mode    = CAMERA_GRAB_LATEST,  // luôn lấy frame mới nhất
        .fb_location  = has_psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM,
    };

    if (has_psram) {
        ESP_LOGI(
            TAG,
            "📸 Camera: xclk=%d frame=%d jpeg_q=%d fb=%d | PSRAM (%.1f MB)",
            GOOUUU_CAM_XCLK_HZ,
            GOOUUU_CAM_FRAME_SIZE_PSRAM,
            GOOUUU_CAM_JPEG_QUALITY_PSRAM,
            GOOUUU_CAM_FB_COUNT_PSRAM,
            psram_size / 1048576.0f
        );
    } else {
        ESP_LOGW(
            TAG,
            "⚠️ Camera: xclk=%d frame=%d jpeg_q=%d fb=%d | DRAM (Không PSRAM)",
            GOOUUU_CAM_XCLK_HZ,
            GOOUUU_CAM_FRAME_SIZE_NO_PSRAM,
            GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM,
            GOOUUU_CAM_FB_COUNT_NO_PSRAM
        );
    }

    return cfg;
}

const char *goouuu_camera_framesize_to_string(framesize_t framesize)
{
    for (size_t i = 0; i < sizeof(s_framesizes) / sizeof(s_framesizes[0]); i++) {
        if (s_framesizes[i].framesize == framesize) {
            return s_framesizes[i].name;
        }
    }
    return "UNKNOWN";
}

bool goouuu_camera_parse_framesize(const char *value, framesize_t *out)
{
    if (!value || !value[0] || !out) {
        return false;
    }

    char normalized[16];
    size_t len = strlen(value);
    if (len >= sizeof(normalized)) {
        return false;
    }

    for (size_t i = 0; i <= len; i++) {
        normalized[i] = (char)toupper((unsigned char)value[i]);
    }

    for (size_t i = 0; i < sizeof(s_framesizes) / sizeof(s_framesizes[0]); i++) {
        if (strcmp(normalized, s_framesizes[i].name) == 0) {
            *out = s_framesizes[i].framesize;
            return true;
        }
    }

    return false;
}

esp_err_t goouuu_camera_apply_stream_profile(void)
{
    sensor_t *s = esp_camera_sensor_get();
    size_t psram_size = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    bool has_psram = (psram_size >= GOOUUU_CAM_MIN_PSRAM_BYTES);
    framesize_t frame_size = has_psram ? GOOUUU_CAM_FRAME_SIZE_PSRAM : GOOUUU_CAM_FRAME_SIZE_NO_PSRAM;
    int jpeg_quality = has_psram ? GOOUUU_CAM_JPEG_QUALITY_PSRAM : GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM;

    if (!s) {
        return ESP_FAIL;
    }

    s->set_exposure_ctrl(s, 0);
    s->set_aec2(s, 0);
    s->set_aec_value(s, GOOUUU_CAM_AEC_VALUE);
    s->set_gain_ctrl(s, 0);
    s->set_agc_gain(s, GOOUUU_CAM_AGC_GAIN);
    s->set_gainceiling(s, GAINCEILING_8X);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_brightness(s, 0);
    s->set_contrast(s, 2);
    s->set_saturation(s, 0);
    s->set_sharpness(s, 2);
    s->set_denoise(s, 1);
    s->set_special_effect(s, 0);
    s->set_lenc(s, 1);
    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);
    s->set_hmirror(s, 1);
    s->set_vflip(s, 0);
    s->set_quality(s, jpeg_quality);
    s->set_framesize(s, frame_size);

    ESP_LOGI(
        TAG,
        "✅ Camera: Đã áp dụng stream profile OV5640 (Frame=%s, JPEG q=%d, AEC=%d, AGC=%d)",
        goouuu_camera_framesize_to_string(frame_size),
        jpeg_quality,
        GOOUUU_CAM_AEC_VALUE,
        GOOUUU_CAM_AGC_GAIN
    );
    return ESP_OK;
}
