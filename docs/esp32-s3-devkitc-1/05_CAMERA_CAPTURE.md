# 05 - Camera Và Capture Task

## 1. Board camera đang chốt

Camera dùng trong đồ án:

- board: `ESP32 Cam Kit Phát Triển ESP32-S3 N16R8 OV5640 Type-C`
- module: `ESP32-S3-WROOM-1`
- camera: `OV5640`
- flash: `16 MB`
- PSRAM: `8 MB`

## 2. Cấu hình camera mặc định đang dùng trong code

Từ [`goouuu_camera.c`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/src/goouuu_camera.c), firmware hiện đang dùng đúng profile này:

```c
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

    .xclk_freq_hz = 20000000,
    .ledc_timer = LEDC_TIMER_0,
    .ledc_channel = LEDC_CHANNEL_0,

    .pixel_format = PIXFORMAT_JPEG,
    .frame_size = FRAMESIZE_VGA,
    .jpeg_quality = 10,
    .fb_count = 2,
    .grab_mode = CAMERA_GRAB_LATEST,
    .fb_location = CAMERA_FB_IN_PSRAM,
};
```

## 3. Ý nghĩa từng lựa chọn

- `PIXFORMAT_JPEG`
  Phù hợp nhất cho upload qua HTTP.

- `FRAMESIZE_VGA`
  `640x480`, đủ tốt cho nhận diện biển số trong bài toán mô phỏng giao thông.

- `jpeg_quality = 10`
  Chất lượng tốt nhưng vẫn giữ kích thước file vừa phải.

- `fb_count = 2`
  Dùng double buffer để camera chạy mượt hơn.

- `CAMERA_GRAB_LATEST`
  Luôn lấy frame mới nhất, tránh bị trễ queue.

- `CAMERA_FB_IN_PSRAM`
  Tận dụng `8 MB PSRAM` của board N16R8.

## 4. PSRAM và fallback hiện có

Code hiện tại có kiểm tra PSRAM:

- nếu có PSRAM đủ lớn: `fb_count = 2`, `fb_location = CAMERA_FB_IN_PSRAM`
- nếu không có PSRAM: tự hạ xuống `fb_count = 1` và dùng DRAM

Điều này giúp firmware không chết cứng nếu môi trường phần cứng có sai khác.

## 5. Pin camera đang map

Theo [`goouuu_board.h`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/include/goouuu_board.h):

| Tín hiệu | GPIO |
|---------|------|
| `XCLK` | `15` |
| `SIOD` | `4` |
| `SIOC` | `5` |
| `VSYNC` | `6` |
| `HREF` | `7` |
| `PCLK` | `13` |
| `D7` | `16` |
| `D6` | `17` |
| `D5` | `18` |
| `D4` | `12` |
| `D3` | `10` |
| `D2` | `8` |
| `D1` | `9` |
| `D0` | `11` |
| `PWDN` | `-1` |
| `RESET` | `-1` |

## 6. Flow của `camera_task`

```text
camera_task
    -> chụp frame định kỳ
    -> gắn traffic_light_state, operation_mode, tl_state_ms
    -> copy frame sang PSRAM
    -> đẩy vào g_frame_queue
    -> uploader_task lấy ra để upload
```

## 7. Kết luận

Profile camera hiện tại đã khớp với board bạn chốt:

- `ESP32-S3 N16R8`
- `OV5640`
- `Type-C`
- `ESP-IDF`
- `VGA JPEG q=10`
- `double buffer trong PSRAM`
