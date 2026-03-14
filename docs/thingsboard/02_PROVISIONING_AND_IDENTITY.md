# Provisioning Và Định Danh Thiết Bị

## Trạng thái hiện tại

Backend và database hiện hỗ trợ provisioning sync động, nhưng firmware hiện tại trong repo không nên mặc định được hiểu là luôn chạy full ThingsBoard provisioning ở runtime.

## Identity chuẩn

Các field quan trọng:

- `camera_id`
- `tb_device_id`
- `tb_device_name`
- `mac_address`
- `device_name`
- `project_name`
- `fw_version`
- `idf_version`

## Payload provisioning backend hỗ trợ

Xem chuẩn mới tại:

- [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [04_BACKEND_DATABASE.md](/C:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)

## Quy tắc cần nhớ

- `tb_device_name` là khóa lớp ThingsBoard
- `device_name` và `project_name` là identity hiển thị
- backend không nên hardcode tên camera nếu provisioning đã có dữ liệu thật
- `camera_provisioning` là nơi lưu identity động
