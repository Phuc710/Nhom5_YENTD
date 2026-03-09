# Bộ tài liệu ThingsBoard

Thư mục này gom toàn bộ tài liệu chuẩn cho phần `ThingsBoard + MQTT + Provisioning + OTA` của hệ thống.

Mục tiêu của bộ docs này:

- mô tả đúng phần code firmware hiện có
- chuẩn hóa cách match `ESP32 <-> ThingsBoard <-> backend <-> web`
- tách rõ đâu là dữ liệu định danh, đâu là dữ liệu động
- thống nhất luồng provisioning, MQTT, OTA và dashboard vận hành

## Vai trò của ThingsBoard trong hệ thống

ThingsBoard hiện là lớp điều phối thiết bị, không phải nơi xử lý vi phạm.

ThingsBoard chịu trách nhiệm:

- provisioning để cấp `access_token`
- MQTT broker cho telemetry và RPC
- shared attributes để cấu hình thiết bị
- OTA package hoặc OTA URL
- hiển thị trạng thái vận hành thiết bị

ThingsBoard không chịu trách nhiệm:

- kết luận vi phạm
- lưu hồ sơ vi phạm
- xử lý AI detect/OCR
- phục vụ ảnh vi phạm cho web

## Danh sách tài liệu

1. [01_ARCHITECTURE_AND_MATCHING.md](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/01_ARCHITECTURE_AND_MATCHING.md)
   Kiến trúc tổng thể và quy tắc match thiết bị.

2. [02_PROVISIONING_AND_IDENTITY.md](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/02_PROVISIONING_AND_IDENTITY.md)
   Luồng provisioning, token, NVS và định danh thiết bị.

3. [03_MQTT_ATTRIBUTES_RPC.md](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
   Topic MQTT, shared attributes, client attributes, telemetry và RPC.

4. [04_OTA_AND_FIRMWARE_LIFECYCLE.md](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md)
   Luồng OTA, reboot, rollback protection và vòng đời firmware.

5. [05_BACKEND_SYNC_AND_DASHBOARD.md](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md)
   Cách backend sync với ThingsBoard và cách web cảnh sát dùng dữ liệu đó.

6. [06_STANDARD_OPERATION_FLOWS.md](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/06_STANDARD_OPERATION_FLOWS.md)
   Các luồng chuẩn end-to-end cho boot, re-provision, OTA và vận hành thường ngày.

## Kết luận ngắn

Khóa match chuẩn của toàn hệ thống phải là:

- `camera_id`: khóa nghiệp vụ
- `mac_address`: khóa phần cứng
- `tb_device_id` và `access_token`: khóa ThingsBoard
- `ip_address`: dữ liệu động để backend tự cập nhật

Không dùng `ip_address` làm định danh chính.
