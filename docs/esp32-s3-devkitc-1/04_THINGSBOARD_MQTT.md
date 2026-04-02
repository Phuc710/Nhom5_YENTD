# 04 - ThingsBoard MQTT

## 1. Vai trò của ThingsBoard

ThingsBoard (TB) phục vụ như một Device Management Layer (Lớp quản trị thiết bị):

- **Identity**: Cấp Access Token cho thiết bị qua Provisioning Key/Secret.
- **Control**: Nhận lệnh RPC (Reboot, OTA, Trigger Sync) từ Dashboard.
- **Config**: Đồng bộ các thông số Camera (Resolution, Quality) qua Shared Attributes.
- **Telemetry**: Giám sát sức khỏe thiết bị (RSSI, RAM, CPU Temp) theo thời gian thực.

## 2. Kiến Trúc Control Plane

MQTT (ThingsBoard) giờ đây hoạt động như một trung tâm điều khiển hỏa tốc, tách biệt khỏi luồng HTTP Sync (Data Plane).

### 2.1 Thuộc tính (Attributes)
- **Client Attributes**: Gửi một lần lúc kết nối để định danh (`mac_address`, `device_name`, `fw_version`).
- **Shared Attributes**: Nhận cấu hình từ Dashboard (`telemetry_interval_ms`, `capture_interval_ms`).

### 2.2 Giám sát Sức khỏe (Telemetry)
Gửi định kỳ các thông số kỹ thuật chi tiết:
- `free_heap`, `min_free_heap`: Giám sát RAM / Memory Leak.
- `cpu_temp`, `wifi_rssi`: Giám sát phần cứng và mạng.
- `device_state`: (booting, running, degraded, ota, error).
- `light_state`: (RED, YELLOW, GREEN, OFF).

### 2.3 Lệnh Điều Khiển (RPC)
- `reboot`: Khởi động lại thiết bị.
- `trigger_sync`: Ép thiết bị gửi nhịp tim lên AI Backend ngay lập tức.
- `ota`: Cập nhật phần mềm qua mạng.
- `factory_reset`: Xóa NVS qua tầng MQTT.

---
*Tham khảo chi tiết: [MQTT & RPC Specs](../thingsboard/03_MQTT_ATTRIBUTES_RPC.md)*
