# Kiến Trúc Và Quy Tắc Match

## 1. Mô hình hiện tại

```text
ESP32-S3
    -> phát stream nội bộ
    -> có thể gửi provisioning sync về backend
    -> có thể được ThingsBoard quản lý attributes / RPC / OTA

ThingsBoard
    -> quản lý device và identity lớp IoT

Backend
    -> đồng bộ device từ ThingsBoard
    -> upsert cameras + camera_provisioning
    -> chuẩn hóa tên camera và stream URL
    -> proxy stream cho web

Web
    -> chỉ gọi backend
```

## 2. Các lớp định danh

### `camera_id`

- khóa nghiệp vụ của hệ thống
- dùng ở web, backend, DB, zone, violation

### `mac_address`

- khóa phần cứng thật của ESP32
- hữu ích để đối chiếu board vật lý

### `tb_device_name`

- khóa lớp ThingsBoard
- dùng để sync device, gửi RPC, factory reset

### `device_name` và `project_name`

- identity hiển thị lấy từ firmware/provisioning
- giúp bỏ hardcode tên model ở web/backend

### `stream runtime`

- không dùng làm khóa định danh
- chỉ là dữ liệu động phục vụ stream

## 3. Chuỗi match chuẩn

Chuỗi nên hiểu như sau:

`camera_id <-> mac_address <-> tb_device_name <-> device_name/project_name <-> stream runtime`

Trong đó:

- `camera_id` là khóa nghiệp vụ
- `mac_address` là khóa vật lý
- `tb_device_name` là khóa IoT
- `device_name/project_name` là khóa hiển thị
- `stream runtime` là endpoint truy cập

## 4. Quy tắc nguồn sự thật

### Tên hiển thị

DB hiện chuẩn hóa tên theo thứ tự:

1. `cameras.camera_name`
2. `cameras.tb_device_name`
3. `camera_provisioning.device_name`
4. `camera_provisioning.project_name`
5. `camera_provisioning.tb_device_name`
6. fallback `Camera 00x`

### Stream URL

DB hiện chuẩn hóa `stream_url` theo thứ tự:

1. `cameras.stream_url`
2. `stream_scheme + stream_host/ip_address + stream_port + stream_path`

## 5. Ý nghĩa thực tế

- Nếu admin muốn override tay, sửa ở bảng `cameras`.
- Nếu muốn hệ thống tự động, để DB lấy từ `camera_provisioning`.
- Frontend không nên tự ghép tên hoặc tự ghép `http://<ip>:81/stream`.

## 6. Trạng thái hiện tại của repo

Đã có:

- backend sync device từ ThingsBoard
- backend upsert `camera_provisioning`
- backend/web dùng tên động
- backend proxy stream
- schema DB đã hỗ trợ `device_name`, `project_name`, `stream_*`

Chưa nên giả định:

- mọi firmware trong repo đều đang bật provisioning ThingsBoard ở runtime
- mọi stream đều luôn là `http://<ip>:81/stream` theo kiểu hardcode
