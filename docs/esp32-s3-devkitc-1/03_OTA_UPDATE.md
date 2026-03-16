# 03 - OTA Update

Cơ chế OTA (Over-The-Air) cho phép cập nhật firmware từ xa qua HTTPS:

- **Điều phối**: ThingsBoard quản lý các thuộc tính `ota_url`, `target_fw_version` và `idf_version`.
- **Thực thi**: Firmware sử dụng module `esp_https_ota` để tải và ghi flash an toàn.
- **Xác thực**: Hỗ trợ rollback tự động nếu firmware mới không boot thành công hoặc không kết nối được mạng.
- **Trạng thái**: Cập nhật tiến độ `DOWNLOADING`, `UPDATED`, `FAILED` lên ThingsBoard thông qua MQTT attributes.

Đọc thêm:

- [esp32_s3.md](/C:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)
- [thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md)
