# 11 - Board Profile N16R8 OV5640

## Board mục tiêu

Firmware hiện nhắm tới board ESP32-S3 N16R8 dùng camera OV5640.

## Thông số chính

- SoC: ESP32-S3
- Camera: OV5640
- LED RGB: GPIO 48
- BOOT button: GPIO 0

## Camera pin map

Nguồn cấu hình:

- [goouuu_board.h](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/include/goouuu_board.h)

Tài liệu này không lặp lại từng chân nếu code đã là nguồn sự thật.

## Camera profile mặc định

- JPEG
- VGA
- quality 10
- `CAMERA_GRAB_LATEST`
- ưu tiên PSRAM

## Mục tiêu sử dụng

Board profile này hiện được tối ưu cho:

- stream MJPEG cục bộ
- web hosting xem qua backend proxy
- anti-blur tuning cho OV5640

## Ghi chú

Nếu phần cứng thực tế khác flash/PSRAM/camera pin map, phải ưu tiên cấu hình thật trong code và `platformio.ini`.
