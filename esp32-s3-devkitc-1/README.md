# ESP32-S3 AI Camera Firmware - Decoupled Architecture

Bản cập nhật firmware này tái cấu trúc toàn diện hệ thống theo kiến trúc **Chuẩn Maintainer**, tập trung vào sự ổn định, hiệu năng cao và khả năng tự phục hồi. Hệ thống được chia làm hai mặt phẳng điều khiển và dữ liệu (Control & Data Plane) tách biệt hoàn toàn.

---

## 🏗 Kiến trúc Hệ thống

Thiết bị ESP32-S3 đóng vai trò là một **Camera Edge Node**, xử lý thu nhận hình ảnh và gửi báo cáo về hai hệ thống độc lập:

1.  **Control & Data Plane (MQTT-First)**: 
    *   Tất cả trạng thái sống, dữ liệu cảm biến và đếm ngược đèn giao thông được dồn vào **MQTT Telemetry**.
    *   Loại bỏ hoàn toàn HTTP Heartbeat định kỳ để giải phóng tài nguyên CPU cho camera.
2.  **AI Data Plane (HTTP MJPEG)**:
    *   Chỉ sử dụng HTTP cho việc đăng ký IP ban đầu (Provisioning) và truyền tải luồng video MJPEG.

---

## ⚡️ Luồng Hoạt động (System Flow)

1.  **Phase 1: Boot & Hardware Init**
    *   Khởi tạo NVS, cấu hình phần cứng Camera.
    *   Kết nối WiFi (ưu tiên reconnect nhanh theo cấu hình NVS).
2.  **Phase 2: Task Orchestration**
    *   `main.c` chuyển quyền điều khiển cho `task_manager.c`.
    *   Mở Server MJPEG ngay lập tức (không block).
3.  **Phase 3: Control & Data Sync**
    *   `mqtt_task` tự động thực hiện **Provisioning ThingsBoard** nếu chưa có token.
    *   Ngay khi có token, `backend_sync` task được kích hoạt để thực hiện:
        *   **Provisioning Backend HTTP** (đẩy IP, Stream URL về AI Backend).
        *   Duy trì **Heartbeat** mỗi interval.

---

## 📦 Đặc tả Payload (Slim & Fast)

Để tối ưu hóa tài nguyên mạng, payload đã được tinh giản chỉ giữ lại các trường cốt lõi.

### 1. Backend Provisioning (HTTP POST - `/api/cameras/provision`)
Gửi khi thiết bị vừa boot hoặc reset token.

```json
{
  "camera_id": 1,
  "camera_name": "Cam Hieu-A1",
  "tb_device_name": "cam-8A9B0C1D2E3F",
  "mac_address": "8A:9B:0C:1D:2E:3F",
  "ip_address": "192.168.1.15",
  "stream_url": "http://192.168.1.15:81/stream",
  "location": "Nga tu A"
}
```

```json
{
  "light_state": "RED",
  "remain_sec": 5,
  "operation_mode": "normal",
  "device_state": "running",
  "rssi": -45,
  "free_heap": 123456
}
```

### 2. ThingsBoard Health Telemetry (MQTT - 60s/lần)
Chứa các dữ liệu kỹ thuật chi tiết hơn:
*   `min_free_heap`, `cpu_temp`, `uptime_s`, `wifi_disconnect_count`.

### 3. Backend Provisioning (HTTP POST - One-time)
Gửi 1 lần duy nhất khi boot để báo IP cho Backend.
```json
{
  "camera_id": 1,
  "ip_address": "192.168.1.15",
  "stream_url": "http://192.168.1.15:81/stream",
  "mac_address": "8A:9B:0C:1D:2E:3F"
}
```

### 3. ThingsBoard Telemetry (MQTT)
Chứa các dữ liệu kỹ thuật chi tiết không cần đẩy lên AI Backend.
*   `free_heap`, `min_free_heap`, `wifi_rssi`, `cpu_temp`, `uptime_s`.
*   `device_state` (booting, running, degraded, error, ota).
*   `light_state` snapshot chuyên sâu cho dashboard.

---

## 🛡 Khả năng Tự phục hồi (Self-Healing)

### 🧩 Circuit Breaker & Degraded Mode
Nếu Backend HTTP sập hoặc phản hồi quá chậm (timeout):
1.  Sau **3 lần** lỗi liên tiếp, thiết bị tự rơi vào trạng thái `DEGRADED`.
2.  Trong `DEGRADED`, interval gửi HTTP sẽ giãn ra **60s** (thay vì 5s) để giảm tải và tránh treo task.
3.  Hệ thống tự động reset về trạng thái `RUNNING` ngay khi có 1 request thành công.

### 🧩 Sync Inflight Control
Cơ chế khóa chặn không cho phép gửi request mới nếu request cũ chưa hoàn tất. Ngăn ngừa tình trạng rò rỉ bộ nhớ hoặc spam TCP khi mạng lag.

### 🧩 Hardware Factory Reset
*   **Hành động**: Nhấn giữ nút **BOOT** (GPIO 0) trên board trong **3 giây**.
*   **Phản hồi**: LED nháy đỏ nhịp thở khi đang giữ. Nháy nhanh 5 lần khi hoàn tất xóa NVS.
*   **Kết quả**: Thiết bị xóa sạch cấu hình WiFi, Token, và reboot về trạng thái mới.

---

## 🔍 Log Standards
Sử dụng log format sau để thuận tiện cho debugging qua Serial Monitor:
*   `NET  |`: Trạng thái mạng/IP.
*   `CFG  |`: Thao tác ghi/nạp NVS.
*   `PROV |`: Tiến trình lấy Token ThingsBoard.
*   `HB   |`: Trạng thái Backend Sync (HTTP).
*   `RPC  |`: Các lệnh điều khiển hỏa tốc từ dashboard.

---

## ⚙️ Cấu hình build (`platformio.ini`)
Để kích hoạt đầy đủ tính năng, đảm bảo các build flags sau được set:
*   `BACKEND_SYNC_RETRY_MS=60000` (Degraded interval)
*   `BACKEND_HEARTBEAT_INTERVAL_MS=5000` (Nhịp tim bình thường)
*   `WATCHDOG_TIMEOUT_SEC=60` (Watchdog hệ thống)
*   `BACKEND_UPLOAD_URL` (Địa chỉ AI Backend)
*   `MQTT_BROKER_URI` (Địa chỉ ThingsBoard)
