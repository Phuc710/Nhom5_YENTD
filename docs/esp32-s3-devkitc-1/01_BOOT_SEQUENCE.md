# 01 - Boot Sequence

## Trạng thái hiện tại

Boot flow firmware hiện tại nên hiểu theo hướng:

1. khởi tạo NVS
2. đọc config
3. khởi tạo LED trạng thái
4. kết nối WiFi
5. khởi tạo camera/task runtime
6. mở HTTP stream server

## Nguồn sự thật

- [main.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/main.c)
- [task_manager.c](/C:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/main/task_manager.c)
- [esp32_s3.md](/C:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)

## Ghi chú

Các boot flow cũ có provisioning/MQTT/upload đầy đủ không còn nên được xem là tài liệu lịch sử nếu không xuất hiện trong code runtime hiện tại.
