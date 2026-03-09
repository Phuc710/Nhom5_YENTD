# 11 - Board Profile N16R8 OV5640 Type-C

## 1. Tên board dùng trong đồ án

Board thực tế:

- `ESP32 Cam Kit Phát Triển ESP32-S3 N16R8 OV5640 Type-C`

Module gốc:

- `ESP32-S3-WROOM-1`

## 2. Thông số phần cứng đã chốt

Theo profile bạn cung cấp, board này được lưu lại với các thông số:

- CPU: `Xtensa LX7 dual-core 32-bit`
- xung nhịp tối đa: `240 MHz`
- ROM: `384 KB`
- SRAM: `512 KB`
- RTC SRAM: `16 KB`
- PSRAM: `8 MB`
- Flash: `16 MB`
- điện áp hoạt động: `3.0V -> 3.6V`
- tối đa `45 GPIO`
- `2 x 12-bit ADC`, tối đa `20 kênh`
- WiFi `IEEE 802.11 b/g/n`
- hỗ trợ băng thông `20 MHz` và `40 MHz` trên `2.4 GHz`
- hỗ trợ tổng hợp khung `TX/RX A-MPDU`, `TX/RX A-MSDU`

## 3. Camera đi kèm

Camera đang chốt:

- `OV5640`
- giao tiếp `DVP`
- kết nối qua đầu camera trên board
- firmware cũng đang mở hỗ trợ `OV2640` và `OV5640`, nhưng board mục tiêu là `OV5640`

## 4. Cấu hình build nên dùng

Trong PlatformIO:

- board env: `esp32-s3-devkitc-1`
- framework: `espidf`
- flash size: `16MB`

Trong repo hiện tại, profile này đã được ghi ở:

- [`platformio.ini.example`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/platformio.ini.example)
- [`goouuu_board.h`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/include/goouuu_board.h)
- [`goouuu_camera.c`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/src/goouuu_camera.c)

## 5. Cấu hình camera mặc định

Profile camera đã lưu:

- `xclk_freq_hz = 20000000`
- `pixel_format = PIXFORMAT_JPEG`
- `frame_size = FRAMESIZE_VGA`
- `jpeg_quality = 10`
- `fb_count = 2`
- `grab_mode = CAMERA_GRAB_LATEST`
- `fb_location = CAMERA_FB_IN_PSRAM`

## 6. Ý nghĩa khi dùng với đồ án

Profile này phù hợp cho bài toán hiện tại vì:

- đủ RAM để giữ double buffer
- JPEG đủ nhẹ để upload qua WiFi
- VGA đủ để nhận diện biển số trong mô hình mô phỏng
- `CAMERA_GRAB_LATEST` giảm trễ hình trong pipeline upload

## 7. Kết luận

Từ đây về sau, khi nhắc đến board firmware trong repo này, mặc định hiểu là:

`ESP32 Cam Kit Phát Triển ESP32-S3 N16R8 OV5640 Type-C`
