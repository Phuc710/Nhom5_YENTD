# OTA Và Vòng Đời Firmware

Hệ thống hỗ trợ cập nhật firmware từ xa (Over-The-Air) qua giao thức HTTPS, được quản lý bởi ThingsBoard.

## 1. Cơ Chế Kích Hoạt OTA

Firmware hỗ trợ hai cách kích hoạt cập nhật:

### Cách 1: Qua Shared Attributes (Tự động)
Khi ThingsBoard cập nhật các thuộc tính sau:
- `target_fw_version`: Phiên bản bạn muốn nâng cấp lên.
- `ota_url`: Link tải file `.bin`.
Thiết bị sẽ so sánh `target_fw_version` với phiên bản hiện tại. Nếu khác nhau, nó sẽ tự động tải file từ `ota_url`.

### Cách 2: Qua RPC (Chủ động)
Gửi lệnh RPC `startOTA` với tham số `url`. Thiết bị sẽ bắt đầu quá trình cập nhật ngay lập tức mà không cần kiểm tra phiên bản.

## 2. Trạng Thái Cập Nhật (FW State)

Trong quá trình OTA, thiết bị sẽ gửi thuộc tính `fw_state` lên ThingsBoard để người quản trị theo dõi:
- `DOWNLOADING`: Đang tải file firmware.
- `UPDATED`: Tải và ghi flash thành công, đang chờ khởi động lại.
- `FAILED`: Gặp lỗi (kèm theo `fw_error` - mã lỗi ESP-IDF).

## 3. Quy Trình Boot & Verify

1. **Khởi động**: Sau khi ghi firmware mới, ESP32 sẽ tự restart.
2. **Verify**: ESP32 sử dụng cơ chế Anti-rollback. Nếu firmware mới boot thành công và kết nối được WiFi/ThingsBoard, nó sẽ được đánh dấu là `Valid`. Nếu boot lỗi, ESP32 sẽ tự động quay về phiên bản cũ (Rollback).
3. **Identity**: Sau khi OTA thành công, `fw_version` trên Client Attribute sẽ tự động cập nhật lên phiên bản mới.

## Source of truth

- [esp32_s3.md](../esp32_s3.md)
- [02_BACKEND_API_V1.md](../02_BACKEND_API_V1.md)
