# 05 - Camera Capture

## Phần cứng mục tiêu

- ESP32-S3 N16R8
- OV5640
- PSRAM

## Cấu hình camera hiện tại

Profile hiện tại bám theo code firmware:

- `xclk_freq_hz = 20000000`
- `pixel_format = PIXFORMAT_JPEG`
- `frame_size = FRAMESIZE_VGA`
- `jpeg_quality = 10` khi có PSRAM
- `fb_count = 2` khi có PSRAM
- `grab_mode = CAMERA_GRAB_LATEST`
- `fb_location = CAMERA_FB_IN_PSRAM`

Nếu không đủ PSRAM:

- giảm `fb_count`
- có thể dùng frame size nhỏ hơn theo config fallback

## Stream profile anti-blur

Sau `esp_camera_init()`, firmware áp thêm tuning:

- **Gương & Xoay**: `hmirror = 1`, `vflip = 0`.
- **Tuning**: `contrast = 2`, `sharpness = 2`, `denoise = 1`.
- **Anti-Blur**: Tắt AEC/AGC tự động, cấu hình exposure và gain thủ công để bám sát điều kiện ánh sáng thực tế, triệt tiêu hiện tượng nhòe khi đối tượng di chuyển nhanh.

## Ý nghĩa

Mục tiêu là:

- stream mượt
- ít motion blur
- ảnh nét hơn cho quan sát và OCR nếu cần

## Stream endpoint

Chuẩn hiện tại là:

- `http://<ip>:81/stream`

Không nên hiểu theo dạng cũ thiếu port.

## Source of truth

- [goouuu_camera.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/goouuu_camera.c)
- [esp32_s3.md](/C:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)
