#pragma once

#include "esp_camera.h"

// Defaults can be overridden via build flags if needed.
#ifndef GOOUUU_CAM_FRAME_SIZE_PSRAM
#define GOOUUU_CAM_FRAME_SIZE_PSRAM FRAMESIZE_HVGA
#endif
#ifndef GOOUUU_CAM_FRAME_SIZE_NO_PSRAM
#define GOOUUU_CAM_FRAME_SIZE_NO_PSRAM FRAMESIZE_QVGA
#endif
#ifndef GOOUUU_CAM_MIN_PSRAM_BYTES
#define GOOUUU_CAM_MIN_PSRAM_BYTES (2 * 1024 * 1024)
#endif
#ifndef GOOUUU_CAM_JPEG_QUALITY_PSRAM
#define GOOUUU_CAM_JPEG_QUALITY_PSRAM 10
#endif
#ifndef GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM
#define GOOUUU_CAM_JPEG_QUALITY_NO_PSRAM 12
#endif
#ifndef GOOUUU_CAM_FB_COUNT_PSRAM
#define GOOUUU_CAM_FB_COUNT_PSRAM 2
#endif
#ifndef GOOUUU_CAM_FB_COUNT_NO_PSRAM
#define GOOUUU_CAM_FB_COUNT_NO_PSRAM 1
#endif

#ifndef GOOUUU_CAMERA_USE_SCCB_FIELDS
#define GOOUUU_CAMERA_USE_SCCB_FIELDS 0
#endif

camera_config_t goouuu_camera_config_default(void);
