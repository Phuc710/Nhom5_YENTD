# OTA Và Vòng Đời Firmware

## Ghi chú chuẩn hóa

OTA qua ThingsBoard hiện nên xem là capability mở rộng của hệ thống, không phải flow bắt buộc phải đang bật trong mọi build firmware của repo.

## Nếu dùng OTA

ThingsBoard nên giữ:

- version mục tiêu
- URL gói firmware
- RPC/attribute điều phối OTA

Backend nên giữ:

- thông tin firmware hiện tại cho dashboard
- lịch sử provisioning/runtime cần thiết

## Source of truth

- [esp32_s3.md](/C:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)
- [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
