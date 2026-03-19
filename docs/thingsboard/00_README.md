# Bộ Tài Liệu ThingsBoard

Thư mục này mô tả vai trò của ThingsBoard trong kiến trúc hiện tại.

## Vai trò hiện tại

ThingsBoard là lớp điều phối thiết bị:

- quản lý device
- giữ shared attributes
- nhận telemetry
- gửi RPC
- OTA

ThingsBoard không phải:

- nguồn API trực tiếp cho web
- nơi dựng dashboard nghiệp vụ
- nơi lưu violation

## Match chuẩn giữa các lớp

`ESP32-S3 <-> ThingsBoard <-> Backend <-> Web`

Quy tắc:

- Web đọc backend
- Backend đọc DB và sync với ThingsBoard
- Device identity không nên hardcode ở frontend/backend

## Bộ field identity cần hiểu đúng

- `camera_id`: khóa nghiệp vụ
- `tb_device_name`: khóa lớp ThingsBoard
- `mac_address`: khóa phần cứng
- `device_name`: tên thiết bị gửi từ firmware
- `project_name`: code name / project name của firmware
- `stream_*`: thông tin dựng URL stream động

## Tài liệu nên đọc tiếp

1. [01_ARCHITECTURE_AND_MATCHING.md](./01_ARCHITECTURE_AND_MATCHING.md)
2. [05_BACKEND_SYNC_AND_DASHBOARD.md](./05_BACKEND_SYNC_AND_DASHBOARD.md)

Lưu ý:

- Một số file cũ trong thư mục này vẫn mô tả flow MQTT/provisioning đầy đủ của firmware đời trước.
- Khi có mâu thuẫn, ưu tiên code hiện tại, [database/schema.sql](../../database/schema.sql), rồi mới đến docs chi tiết cũ.
