/*
 * goouuu_camera.c - Camera configuration helpers for GOOUUU ESP32-S3-CAM.
 */
#include "goouuu_camera.h"

#include <ctype.h>
#include <string.h>

#include "esp_camera.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "goouuu_board.h"

static const char *TAG = "goouuu_cam";
static bool s_safe_mode_active = false;

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

static camera_config_t build_camera_config(bool safe_mode)
{
    size_t psram_size = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    bool has_psram = (psram_size >= GOOUUU_CAM_MIN_PSRAM_BYTES);
    size_t fb_count = has_psram ? GOOUUU_CAM_FB_COUNT_PSRAM : GOOUUU_CAM_FB_COUNT_NO_PSRAM;
    camera_grab_mode_t grab_mode = (fb_count > 1) ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;

    if (safe_mode) {
        fb_count = 1;
        grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    }

    camera_config_t cfg = {
        .pin_pwdn = CAM_PIN_PWDN,
        .pin_reset = CAM_PIN_RESET,
        .pin_xclk = CAM_PIN_XCLK,
        .pin_sccb_sda = CAM_PIN_SIOD,
        .pin_sccb_scl = CAM_PIN_SIOC,
        .pin_d7 = CAM_PIN_D7,
        .pin_d6 = CAM_PIN_D6,
        .pin_d5 = CAM_PIN_D5,
        .pin_d4 = CAM_PIN_D4,
        .pin_d3 = CAM_PIN_D3,
        .pin_d2 = CAM_PIN_D2,
        .pin_d1 = CAM_PIN_D1,
        .pin_d0 = CAM_PIN_D0,
        .pin_vsync = CAM_PIN_VSYNC,
        .pin_href = CAM_PIN_HREF,
        .pin_pclk = CAM_PIN_PCLK,
        .xclk_freq_hz = GOOUUU_CAM_XCLK_HZ,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = GOOUUU_CAM_PIXEL_FORMAT,
        .frame_size = has_psram ? GOOUUU_CAM_FRAME_SIZE_PSRAM : GOOUUU_CAM_FRAME_SIZE_NO_PSRAM,
        .jpeg_quality = has_psram ? GOOUUU_CAM_JPEG_QUALITY_PSRAM : GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM,
        .fb_count = fb_count,
        .grab_mode = grab_mode,
        .fb_location = has_psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM,
    };

    ESP_LOGI(
        TAG,
        "Camera %sconfig: xclk=%d frame=%d jpeg_q=%d fb=%u grab=%s psram=%.1fMB",
        safe_mode ? "SAFE " : "",
        GOOUUU_CAM_XCLK_HZ,
        cfg.frame_size,
        cfg.jpeg_quality,
        (unsigned)cfg.fb_count,
        cfg.grab_mode == CAMERA_GRAB_LATEST ? "latest" : "when_empty",
        psram_size / 1048576.0f
    );

    return cfg;
}

camera_config_t goouuu_camera_config_default(void)
{
    return build_camera_config(false);
}

camera_config_t goouuu_camera_config_safe(void)
{
    return build_camera_config(true);
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

    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_brightness(s, 1);     // +1 sáng hơn mặc định
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);
    s->set_ae_level(s, 1);       // +1 AE target sáng hơn (tránh tối)
    s->set_sharpness(s, 1);
    s->set_denoise(s, 1);
    s->set_special_effect(s, 0);
    s->set_lenc(s, 1);
    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);
    s->set_hmirror(s, GOOUUU_CAM_HMIRROR);
    s->set_vflip(s, GOOUUU_CAM_VFLIP);
    s->set_quality(s, jpeg_quality);
    s->set_framesize(s, frame_size);

    ESP_LOGI(
        TAG,
        "Camera profile applied (%s mode, frame=%s, jpeg_q=%d, AE=auto, AGC=auto, hmirror=%d, vflip=%d)",
        s_safe_mode_active ? "safe" : "normal",
        goouuu_camera_framesize_to_string(frame_size),
        jpeg_quality,
        GOOUUU_CAM_HMIRROR,
        GOOUUU_CAM_VFLIP
    );
    return ESP_OK;
}

esp_err_t goouuu_camera_recover_safe_mode(void)
{
    if (s_safe_mode_active) {
        ESP_LOGI(TAG, "Camera recovery skipped: safe mode already active");
        return ESP_OK;
    }

    ESP_LOGW(TAG, "Camera recovery: switching to safe mode");

    if (esp_camera_get_psram_mode()) {
        esp_err_t dma_err = esp_camera_set_psram_mode(false);
        if (dma_err != ESP_OK) {
            ESP_LOGE(TAG, "Camera recovery: cannot disable PSRAM DMA (%s)", esp_err_to_name(dma_err));
            return dma_err;
        }
    }

    camera_config_t safe_cfg = goouuu_camera_config_safe();
    esp_err_t err = esp_camera_reconfigure(&safe_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera recovery: reconfigure failed (%s)", esp_err_to_name(err));
        return err;
    }

    s_safe_mode_active = true;
    err = goouuu_camera_apply_stream_profile();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Camera recovery: profile apply failed (%s)", esp_err_to_name(err));
    }
    return err;
}

bool goouuu_camera_safe_mode_active(void)
{
    return s_safe_mode_active;
}
