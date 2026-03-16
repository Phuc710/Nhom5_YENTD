# 11 - Board Profile N16R8 OV5640

Firmware được tối ưu hóa cho board **GOOUUU ESP32-S3-CAM** (N16R8) tích hợp sensor **OV5640**.

## 1. Thông Số Phần Cứng

- **SoC**: ESP32-S3 (Dual-core, WiFi + Bluetooth LE).
- **RAM**: 8MB PSRAM (OPI) phục vụ buffer camera.
- **Flash**: 16MB SPI Flash.
- **Camera**: OV5640 (5.0 MegaPixel).
- **Peripherals**: 
  - RGB LED (WS2812B): GPIO 48.
  - BOOT Button: GPIO 0.

## 2. Cấu Hình Pin Map

Chân tín hiệu Camera được định nghĩa tập trung tại [goouuu_board.h](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/include/goouuu_board.h). Hệ thống sử dụng interface chuẩn của ESP32 Camera Driver.

## 3. Tối Ưu Hóa "Stream-First"

Board profile này được tinh chỉnh đặc biệt cho việc phát video thời gian thực:

- **Anti-blur**: Cấu hình Exposure và Gain thủ công để giảm nhòe chuyển động.
- **Dual Buffer**: Sử dụng 2 framebuffer trong PSRAM để tăng tốc độ capture.
- **VGA Native**: Ưu tiên resolution 640x480 để cân bằng giữa độ nét và độ trễ.
- **Backend Relay**: Tương thích hoàn toàn với lớp proxy của Backend giúp xem video từ xa ổn định.

---
*Lưu ý: Nếu thay đổi sang model board khác (như AI-Thinker), cần cập nhật lại Pin Map trong header file tương ứng.*
