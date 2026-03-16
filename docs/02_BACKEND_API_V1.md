# API Backend V1

Tài liệu này mô tả contract API đang phù hợp với backend hiện tại.

## 1. Quy ước chung

- Prefix chung: `/api`
- Framework: FastAPI
- Frontend chỉ gọi backend
- ThingsBoard không phải API trực tiếp cho web

## 2. System endpoints

### `GET /`

Trả metadata cơ bản của backend.

### `GET /health`

Trả trạng thái backend, gồm:

- `status`
- `timestamp`
- `supabase_auth_mode`
- `cors_origins`
- `thingsboard_sync_enabled`
- `thingsboard_sync_interval_seconds`

## 3. Camera endpoints

### `GET /api/cameras`

- Nguồn dữ liệu: `view_camera_summary`
- Dùng cho danh sách camera và dashboard

### `GET /api/cameras/{camera_id}`

- Lấy chi tiết một camera
- Response có thể gồm cả dữ liệu động từ provisioning:
  - `device_name`
  - `project_name`
  - `device_model`
  - `wifi_ssid`
  - `resolution`
  - `stream_scheme`
  - `stream_host`
  - `stream_port`
  - `stream_path`
  - `stream_snapshot_path`
  - `configured_camera_name`
  - `configured_stream_url`

### `POST /api/cameras`

- Tạo camera thủ công từ backend/web

### `PUT /api/cameras/{camera_id}`

- Cập nhật metadata camera
- Các field thường dùng:
  - `camera_name`
  - `location`
  - `stream_url`
  - `description`
  - `tb_device_name`
  - `status`

### `DELETE /api/cameras/{camera_id}`

- Xóa camera

### `POST /api/cameras/{camera_id}/factory-reset`

- Backend gọi REST API ThingsBoard
- ThingsBoard gửi RPC `factoryReset` tới thiết bị theo `tb_device_name`

### `POST /api/cameras/{camera_id}/stream`

Không có endpoint `POST`. Luồng stream dùng:

- `GET /api/cameras/{camera_id}/stream`
- `GET /api/cameras/{camera_id}/snapshot`

### `GET /api/cameras/{camera_id}/stream`

- Proxy MJPEG stream qua backend
- Dùng cho web hosting cùng domain

### `GET /api/cameras/{camera_id}/snapshot`

- Proxy JPEG snapshot qua backend

### `GET /api/cameras/{camera_id}/live-view`

- Payload gọn cho overlay stream (chứa tọa độ Bounding Box, FPS, Latency):
  - `camera_id`
  - `camera_name`
  - `device_label`
  - `location`
  - `stream_url`
  - `online`
  - `timezone`
  - `server_time`
  - `overlay`

### `GET /api/cameras/{camera_id}/live-view/sse`

- Luồng **Server-Sent Events (SSE)** đẩy dữ liệu AI Bounding Box liên tục (Real-time).
- Trông chờ EventSource kết nối từ frontend để stream tọa độ. Băng thông cực thấp và 0% CPU.

### `POST /api/cameras/provision`

Endpoint này dùng để ESP32 hoặc một lớp bridge gửi identity/provisioning về backend.

Payload hỗ trợ:

```json
{
  "camera_id": 1,
  "tb_device_id": "device-id",
  "tb_device_name": "cam-AABBCCDDEEFF",
  "device_name": "Cam-A1B2C3",
  "project_name": "esp32-s3-cam-firmware",
  "device_model": "ESP32S3-CAM",
  "wifi_ssid": "Office-WiFi",
  "resolution": "VGA",
  "access_token": "token",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "fw_version": "1.0.0",
  "idf_version": "v5.3.1",
  "stream_scheme": "http",
  "stream_host": "192.168.1.10",
  "stream_port": 81,
  "stream_path": "/stream",
  "stream_snapshot_path": "/snapshot",
  "ip_address": "192.168.1.10",
  "last_boot_at": "2026-03-13T08:30:00Z"
}
```

Hành vi backend:

- upsert `camera_provisioning`
- tạo camera nếu chưa có
- cập nhật `status=active`
- **Quy tắc Match**: Ưu tiên khớp theo `mac_address` (Hard Anchor) trước khi tìm theo `tb_device_name`. Điều này đảm bảo tính nhất quán của thiết bị vật lý.
- Nếu `camera_name` hiện tại chỉ là placeholder thì thay bằng tên thật.
- Nếu `stream_url` hiện tại là URL tự sinh cũ hoặc đang trống thì cập nhật sang URL động mới.

### `POST /api/cameras/sync-devices`

- Quét device từ ThingsBoard.
- **Auto Mapping**: Chuyển đổi các key từ ThingsBoard về chuẩn Backend:
  - `idf_ver` ➔ `idf_version`
  - `Light_Mode` ➔ `light_mode`
  - Chuẩn hóa giá trị status/light_mode về **lowercase**.
- Cố lấy thêm attributes/telemetry mới nhất theo kiểu best-effort để đồng bộ `device_name`, `project_name`, `stream_*`, `ip_address`, `online`.
- upsert về DB.

## 4. Dashboard endpoints

### `GET /api/dashboard/overview`

- tổng số camera
- số camera online/offline
- violations hôm nay
- violations tổng

### `GET /api/dashboard/cameras`

- dữ liệu camera cho dashboard

### `GET /api/dashboard/recent-violations?limit=10`

- violations gần nhất

### `GET /api/dashboard/stats/hourly`

- Thống kê vi phạm theo từng khung giờ trong ngày hôm nay.
- Format JSON trả về đã chuẩn hóa để FrontEnd `Chart.js` render lập tức (ví dụ: `{"08": 15, "09": 22}`).

### `GET /api/dashboard/stats/weekly`

- Thống kê vi phạm theo tuần (Trend 7 ngày gần nhất).

### `GET /api/dashboard/stats/camera`

- Thống kê số điểm nghi vấn vi phạm theo từng Camera riêng biệt.

## 5. System Settings endpoints

### `GET /api/settings/system`

- Lấy ra cấu hình của hệ thống từ tệp tin `.env` (MQTT Host, AI Threshold, Server Retention Time).

### `PUT /api/settings/system`

- Thay đổi cấu hình tệp `.env` trực tiếp từ giao diện Admin. Đòi hỏi Reload Backend để aply giá trị mới.

## 6. Zone endpoints

### `GET /api/cameras/{camera_id}/zones`

- lấy zone theo camera

### `PUT /api/cameras/{camera_id}/zones`

- thay toàn bộ zone của camera

## 7. Identity chain chuẩn

Chuỗi match chuẩn hiện tại (theo thứ tự ưu tiên):

**`mac_address` (Anchor)** ➔ `camera_id` (Business) ➔ `tb_device_name` (IoT) ➔ `device_name/project_name` (Label)

Trong đó:

- `camera_id`: khóa nghiệp vụ
- `mac_address`: khóa phần cứng
- `tb_device_name`: khóa lớp ThingsBoard
- `device_name` / `project_name`: identity hiển thị từ thiết bị
- `stream runtime`: URL stream động từ provisioning hoặc override thủ công

## 8. Ghi chú

- `stream_url` trả ra cho web là giá trị đã chuẩn hóa qua Proxy của Server Backend (Asyncio Queue/PubSub).
- `configured_stream_url` là giá trị override gốc trong bảng `cameras`.
- Repo hiện chuẩn hóa một flow backend duy nhất: camera/provision/stream/dashboard. Các endpoint upload/finalize cũ không còn là một phần của contract API chính.
