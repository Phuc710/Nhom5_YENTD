# Backend Sync Và Dashboard

## 1. Mục tiêu

Backend phải là lớp chuẩn hóa để dashboard không phụ thuộc trực tiếp vào ThingsBoard.

Điều web cần là:

- tên camera đúng
- vị trí
- online/offline
- stream ổn định
- metadata thiết bị cần thiết

## 2. Backend hiện đồng bộ những gì

Từ ThingsBoard hoặc provisioning sync, backend có thể lưu:

- `tb_device_id`
- `tb_device_name`
- `device_name`
- `project_name`
- `device_model`
- `wifi_ssid`
- `resolution`
- `fw_version`
- `idf_version`
- `mac_address`
- `ip_address`
- `stream_scheme`
- `stream_host`
- `stream_port`
- `stream_path`
- `stream_snapshot_path`
- `last_seen_at`
- `last_boot_at`
- `online`

## 3. Luồng sync chuẩn

### Từ ThingsBoard

1. Backend quét device bằng sync nền hoặc `POST /api/cameras/sync-devices`.
2. Match theo `tb_device_name`.
3. Upsert `cameras` và `camera_provisioning`.
4. Web thấy camera mới qua `view_camera_summary`.

### Từ ESP32 provisioning

1. Thiết bị gửi `POST /api/cameras/provision`.
2. Backend lưu identity/runtime vào `camera_provisioning`.
3. Nếu camera hiện chỉ có placeholder name, backend thay bằng tên thật.
4. Nếu `stream_url` không có override tay, backend cho phép DB dựng stream động.

## 4. Dashboard nên dùng gì

Nên dùng từ backend:

- `camera_name`
- `location`
- `online`
- `last_seen_at`
- `stream_url`
- `fw_version`
- `device_model`
- `resolution`
- `violations_today`
- `violations_total`

Không nên đẩy thẳng ra frontend:

- `access_token`
- raw MQTT payload
- provisioning credentials

## 5. Stream cho web hosting

Luồng đúng hiện tại:

1. Backend lấy `stream_url` đã chuẩn hóa từ DB/view.
2. Frontend dùng `GET /api/cameras/{id}/stream`.
3. Snapshot list/card dùng `GET /api/cameras/{id}/snapshot`.

Kết quả:

- web không cần biết IP thật của camera
- web không cần hardcode port/path
- đổi domain hosting không làm gãy flow

## 6. Kết luận

ThingsBoard là lớp device-control.
Backend là lớp data-contract cho web.
DB là nơi chuẩn hóa tên và stream động.
