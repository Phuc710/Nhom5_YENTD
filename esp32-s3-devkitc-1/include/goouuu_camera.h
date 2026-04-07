#pragma once

#include "esp_err.h"
#include "esp_camera.h"

// Defaults can be overridden via build flags if needed.
#ifndef GOOUUU_CAM_XCLK_HZ
#define GOOUUU_CAM_XCLK_HZ 20000000
#endif
#ifndef GOOUUU_CAM_PIXEL_FORMAT
#define GOOUUU_CAM_PIXEL_FORMAT PIXFORMAT_JPEG
#endif
#ifndef GOOUUU_CAM_FRAME_SIZE_PSRAM
#define GOOUUU_CAM_FRAME_SIZE_PSRAM FRAMESIZE_VGA
#endif
#ifndef GOOUUU_CAM_FRAME_SIZE_NO_PSRAM
#define GOOUUU_CAM_FRAME_SIZE_NO_PSRAM FRAMESIZE_QVGA
#endif
#ifndef GOOUUU_CAM_MIN_PSRAM_BYTES
#define GOOUUU_CAM_MIN_PSRAM_BYTES (2 * 1024 * 1024)
#endif
#ifndef GOOUUU_CAM_JPEG_QUALITY_PSRAM
#define GOOUUU_CAM_JPEG_QUALITY_PSRAM 12
#endif
#ifndef GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM
#define GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM 15
#endif
#ifndef GOOUUU_CAM_FB_COUNT_PSRAM
#define GOOUUU_CAM_FB_COUNT_PSRAM 4
#endif
#ifndef GOOUUU_CAM_FB_COUNT_NO_PSRAM
#define GOOUUU_CAM_FB_COUNT_NO_PSRAM 1
#endif
#ifndef GOOUUU_CAM_ENABLE_PSRAM_DMA
#define GOOUUU_CAM_ENABLE_PSRAM_DMA 0
#endif

#ifndef GOOUUU_CAMERA_USE_SCCB_FIELDS
#define GOOUUU_CAMERA_USE_SCCB_FIELDS 0
#endif
#ifndef GOOUUU_CAM_AEC_VALUE
#define GOOUUU_CAM_AEC_VALUE 120
#endif
#ifndef GOOUUU_CAM_AGC_GAIN
#define GOOUUU_CAM_AGC_GAIN 8
#endif
#ifndef GOOUUU_CAM_HMIRROR
#define GOOUUU_CAM_HMIRROR 0
#endif
#ifndef GOOUUU_CAM_VFLIP
#define GOOUUU_CAM_VFLIP 1
#endif

camera_config_t goouuu_camera_config_default(void);
camera_config_t goouuu_camera_config_safe(void);
esp_err_t goouuu_camera_apply_stream_profile(void);
esp_err_t goouuu_camera_recover_safe_mode(void);
const char *goouuu_camera_framesize_to_string(framesize_t framesize);
bool goouuu_camera_parse_framesize(const char *value, framesize_t *out);
bool goouuu_camera_safe_mode_active(void);
