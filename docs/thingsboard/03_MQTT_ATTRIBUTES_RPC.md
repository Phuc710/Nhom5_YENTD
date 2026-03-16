# MQTT, Attributes, Telemetry Và RPC

Tài liệu này liệt kê chính xác các key và lệnh RPC được hỗ trợ bởi firmware ESP32-S3 và backend hiện tại.

## 1. Attributes (Thuộc tính)

### Shared Attributes (Server ➔ Device)
Cấu hình thiết bị từ xa qua ThingsBoard Dashboard hoặc API:
- `camera_id`: (int) ID camera dùng cho nghiệp vụ.
- `capture_interval_ms`: (int) Khoảng cách giữa 2 lần chụp (mặc định 120ms).
- `jpeg_quality`: (int) Chất lượng nén JPEG (10-15 cho stream tốt).
- `resolution`: (string) Độ phân giải (mặc định "VGA").
- `telemetry_interval_ms`: (int) Tần suất gửi telemetry (mặc định 5000ms).
- `light_mode`: (string) Trạng thái đèn (`red`, `green`, `yellow`, `off`).
- `idf_version`: (string) Phiên bản ESP-IDF (ví dụ `v5.1`).
- `ota_url`: (string) URL chứa firmware `.bin`.
- `reboot`: (bool) Gửi lệnh reboot.
- `factory_reset`: (bool) Xóa NVS và reboot.

### Client Attributes (Device ➔ Server)
- `mac_address`: MAC định danh duy nhất (ví dụ: `AA:BB:CC...`).
- `device_model`: "PCB S3" hoặc "GOOUUU S3".
- `fw_version`: Phiên bản firmware hiện tại.
- `ip_address`: Địa chỉ IP nội bộ cấp bởi router.
- `stream_url`: Endpoint stream MJPEG (thường là `http://<ip>:81/stream`).
- `backend_sync`: Trạng thái đồng bộ với Backend ("synced", "failed", "pending").

## 2. Telemetry (DỮ LIỆU THỜI GIAN THỰC)

- `device_state`: "running", "ota", "error", "wifi_connecting".
- `light_mode`: "red", "green", "yellow", "off" (Đồng bộ với shared attribute).
- `cpu_temp`: Nhiệt độ hoạt động (°C).
- `free_heap`, `min_free_heap`: Bộ nhớ RAM (Bytes).
- `wifi_rssi`: Cường độ tín hiệu WiFi (dBm).
- `uptime_s`: Tổng thời gian chạy (giây).
- `wifi_disconnect_count`: Số lần mất kết nối WiFi.
- `camera_ok`: (bool) Trạng thái cảm biến camera.
- `mqtt_connected`: (bool) Trạng thái kết nối ThingsBoard.

## 3. Remote Procedure Calls (RPC)

| Method | Params | Mô tả |
| :--- | :--- | :--- |
| `setResolution` | `{"framesize": int}` | Đổi độ phân giải (0-15). |
| `setQuality` | `{"quality": int}` | Đổi chất lượng JPEG (4-63). |
| `setInterval` | `{"interval_ms": int}` | Đổi tần suất chụp ảnh. |
| `reboot` | `{}` | Khởi động lại hệ thống. |
| `factoryReset` | `{}` | Xóa NVS và reboot về mode config. |
| `reprovision` | `{}` | Xóa Access Token và chạy lại Provisioning. |
| `startOTA` | `{"url": string}` | Chạy OTA từ URL chỉ định. |
| `getStatus` | `{}` | Request thiết bị gửi snapshot attributes ngay lập tức. |

