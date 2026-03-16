# 01 - Boot Sequence

## Quy trình Boot Chuẩn

1. **Khởi tạo NVS**: Nạp các cấu hình WiFi, Token và định danh từ bộ nhớ flash.
2. **Đọc Cấu Hình**: Ứng dụng load `app_config_t` để xác định mode hoạt động.
3. **LED Trạng Thái**: Khởi tạo LED RGB (GPIO 48) và báo hiệu trạng thái Boot (Đỏ).
4. **Kết Nối WiFi**: Thử kết nối STA. Nếu thất bại, tự động chuyển sang Captive Portal (SoftAP) để người dùng cấu hình lại.
5. **Định Danh Thiết Bị**: Kiểm tra Token ThingsBoard. Nếu chưa có, thực hiện luồng Provisioning.
6. **Task Manager**: Khởi tạo Camera, MQTT, Health và Traffic Light tasks.
7. **Stream Server**: Mở cổng 81 phục vụ stream MJPEG cục bộ.
8. **Hoàn Tất**: LED chuyển sang Xanh Lá / Trắng, hệ thống bắt đầu gửi Telemetry.

## Nguồn sự thật

- [main.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/main.c)
- [task_manager.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/task_manager.c)
- [esp32_s3.md](/C:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)

## Ghi chú

Các boot flow cũ có provisioning/MQTT/upload đầy đủ không còn nên được xem là tài liệu lịch sử nếu không xuất hiện trong code runtime hiện tại.
