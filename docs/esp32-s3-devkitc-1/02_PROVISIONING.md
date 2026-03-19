# 02 - ThingsBoard Provisioning

## Ghi chú chuẩn hóa

Hệ thống hỗ trợ đăng ký kép để đảm bảo đồng bộ hoàn toàn giữa ESP32 và hệ sinh thái:

1. **ThingsBoard Provisioning**: Cấp identity IoT và Access Token để quản trị thiết bị.
2. **Backend Sync**: Đăng ký camera vào hệ thống giám sát nghiệp vụ thông qua API `/provision`.

## Thông Tin Đồng Bộ

Khi thực hiện Provisioning Sync, thiết bị gửi các thông số sau lên Backend:

- `camera_id`: (int) Định danh nghiệp vụ.
- `mac_address`: (string) Định danh vật lý (Hard Anchor).
- `access_token`: (string) Token ThingsBoard MQTT.
- `light_mode`: (string) Trạng thái đèn (`red`, `green`, `yellow`, `off`).
- `idf_version`: (string) Phiên bản ESP-IDF.
- `stream_url`: (string) URL MJPEG nội bộ.
- `fw_version`: (string) Phiên bản firmware.

## Liên Kết Dữ Liệu
Dữ liệu này được Backend sử dụng để tự động ánh xạ Camera vào Dashboard mà không cần sự can thiệp thủ công từ quản trị viên.

---
*Đọc thêm tại: [Architecture & Matching](../thingsboard/01_ARCHITECTURE_AND_MATCHING.md)*
