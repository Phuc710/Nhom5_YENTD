# Backend Sync & Heartbeat

Đảm bảo Custom Backend luôn đồng bộ với trạng thái thực tế của Camera.

## 1. Endpoint Đồng Bộ (ESP32 ➔ Backend)

Firmware ESP32 sử dụng module `mqtt_app.c` để thực hiện REST gọi sang Backend:

- **Provisioning**: `POST /api/cameras/provision`
  - Gọi khi: Thiết bị khởi động hoặc thay đổi `camera_id`/`location`.
  - Body: JSON chứa `mac_address`, `ip_address`, `access_token`, `stream_url`, `camera_id`, `device_name`.
- **Heartbeat**: `POST /api/cameras/heartbeat`
  - Gọi định kỳ mỗi 15 giây (`BACKEND_HEARTBEAT_INTERVAL_MS`).
  - Body: Trạng thái runtime (`resolution`, `wifi_rssi`, `uptime_s`, `device_state`, `free_heap`, `cpu_temp`, `light_mode`).

## 2. Luồng Đồng Bộ ThingsBoard (Backend ➔ TB)

Backend có thể chủ động sync với ThingsBoard qua dịch vụ `IOT-Config`:

- **Sync Devices**: `POST /api/cameras/sync-devices`
  - Backend quét toàn bộ device trên ThingsBoard và map vào Database dựa trên **MAC Address** (ưu tiên) hoặc Tên.
- **Auto Mapping**: Backend đảm bảo đồng bộ hóa các field khác nhau giữa các lớp:
  - `idf_ver` ➔ `idf_version`
  - `Light_Mode` ➔ `light_mode`
  - Giá trị Enum được chuẩn hóa về **lowercase** (ví dụ: `RED` ➔ `red`).

## 3. Quản Lý Stream Đa Kênh (Zero-CPU Pub/Sub)

Mọi yêu cầu xem stream từ Web Dashboard được quản lý tập trung và phân phối qua Backend để bảo vệ ESP32 khỏi việc cạn kiệt tài nguyên (Vi điều khiển chỉ cho phép 1-2 HTTP connection đồng thời):

1. Web Dashboard gọi API Backend (Ví dụ: `GET /api/cameras/{id}/stream`).
2. Backend kiểm tra `stream_url` trong database (cung cấp bởi ESP32 provisioning).
3. Backend tiến hành proxy stream (`StreamingResponse`) thông qua kiến trúc **Asyncio Queue Publish/Subscribe**. Frame ảnh MJPEG từ ESP32 được Backend kéo về 1 lần duy nhất, lưu vào **RAM Cache**, và sau đó phân phối lại cho hàng trăm Web Client cùng lúc với CPU Backend = 0%.
4. Dữ liệu AI Bounding Box được bóc tách và gửi song song qua kênh **Server-Sent Events (SSE)** (`/api/cameras/{id}/live-view/sse`) để Web tự vẽ đè siêu mượt lên Video gốc.

---
*Ghi chú: Luồng đồng bộ và hệ thống PubSub này đảm bảo ESP32 luôn chạy ở mức tải nhẹ nhất (Max FPS), bảo mật IP nội bộ, và mang lại trải nghiệm chuẩn Real-time cho người dùng cuối.*
