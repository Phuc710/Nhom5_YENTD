# 02 - ThingsBoard Provisioning

## Ghi chú chuẩn hóa

File này nay chỉ giữ vai trò mô tả capability provisioning, không khẳng định provisioning đang là runtime flow mặc định của firmware hiện tại.

## Nếu bật provisioning sync

Firmware hoặc bridge có thể gửi:

- `camera_id`
- `tb_device_id`
- `tb_device_name`
- `device_name`
- `project_name`
- `device_model`
- `wifi_ssid`
- `resolution`
- `fw_version`
- `idf_version`
- `stream_*`

về:

- `POST /api/cameras/provision`

## Đọc chuẩn mới

- [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [04_BACKEND_DATABASE.md](/C:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
