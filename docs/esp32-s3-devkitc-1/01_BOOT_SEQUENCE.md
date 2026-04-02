# 01 - Boot Sequence

## Quy trình Boot Chuẩn

1. **Khởi tạo NVS**: Nạp các cấu hình WiFi, Token và định danh từ bộ nhớ flash.
2. **Đọc Cấu Hình**: Ứng dụng load `app_config_t` để xác định mode hoạt động.
3. **LED Trạng Thái**: Khởi tạo LED RGB (GPIO 48) và báo hiệu trạng thái Boot (Đỏ).
4. **WiFi & Network**: Thử kết nối STA. Nếu thất bại, mở portal cấu hình.
5. **Task Manager**: Khởi chạy Camera, MQTT, Health và Traffic Light tasks.
6. **Async Identity (mqtt_task)**: Kiểm tra token TB; nếu thiếu, thực hiện provision tự động mà không block boot.
7. **Backend Sync (backend_sync_task)**: Sau khi có token, thực hiện Provision/Heartbeat lên AI Backend.
8. **Hoàn Tất**: LED xanh/trắng báo sẵn sàng, mở cổng 81 phục vụ stream.

## Nguồn sự thật

- [main.c](../../esp32-s3-devkitc-1/main/main.c)
- [task_manager.c](../../esp32-s3-devkitc-1/main/task_manager.c)
- [esp32_s3.md](../esp32_s3.md)

## Ghi chú

Các boot flow cũ có provisioning/MQTT/upload đầy đủ không còn nên được xem là tài liệu lịch sử nếu không xuất hiện trong code runtime hiện tại.
