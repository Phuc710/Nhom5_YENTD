# Đồng Bộ Backend Và Dashboard

Việc đồng bộ dữ liệu giữa ThingsBoard và Custom Backend là cực kỳ quan trọng để đảm bảo Web hiển thị đúng thông tin thực tế của thiết bị.

## 1. Luồng Đồng Bộ Dữ Liệu

Hệ thống thực hiện đồng bộ qua hai con đường chính:

### Đồng Bộ Từ Thiết Bị (Device-Push)
- **Backend Sync Task**: Khi ESP32 boot hoặc có thay đổi cấu hình quan trọng (như `camera_id`), nó sẽ chạy một task ngầm để POST dữ liệu lên `/api/cameras/provision`.
- **Dữ liệu**: IP, MAC, Access Token, Resolution, Stream URL.
- **Mục tiêu**: Cập nhật bảng `camera_provisioning` và `cameras`.

### Đồng Bộ Từ Backend (Backend-Pull)
- **ThingsBoard Service**: Backend gọi REST API của ThingsBoard để lấy:
  - List devices hiện có.
  - Latest Attributes (Vị trí, config).
  - Latest Telemetry (Nhiệt độ, trạng thái online).
- **Mục tiêu**: Đảm bảo Backend luôn biết trạng thái "IoT Layer" của thiết bị mà không cần chờ thiết bị gửi lên.

## 2. Matching Logic Trong Backend

Backend sử dụng logic sau để liên kết một thiết bị ThingsBoard với một Camera trong hệ thống:

1. **Tìm theo MAC**: Nếu MAC khớp, liên kết với camera đó.
2. **Tìm theo TB Name**: Khớp qua `tb_device_name` (thường là `cam-<MAC>`).
3. **Khởi tạo**: Nếu thiết bị mới hoàn toàn, backend sẽ tự động tạo entry trong bảng `cameras` với ID lấy từ `camera_id` do người dùng cấu hình trên firmware/TB.

## 3. Dashboard Web

Dashboard trên Web (PHP/Vue) không gọi trực tiếp ThingsBoard. Thay vào đó:
1. Web gọi Backend API.
2. Backend API đọc từ Database (đã được đồng bộ từ Device và TB).
3. Kết quả: Tên camera hiển thị "thông minh" (ưu tiên tên người dùng đặt, sau đó đến tên từ provisioning).
 là:

- tên camera đúng
- vị trí
- online/offline
- stream ổn định

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
