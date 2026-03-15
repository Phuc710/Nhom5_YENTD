# MQTT, Attributes, Telemetry Và RPC

Tài liệu này liệt kê chính xác các key và lệnh RPC được hỗ trợ bởi firmware ESP32-S3 và backend hiện tại.

## 1. Attributes (Thuộc tính)

### Shared Attributes (Từ Server xuống Device)
Dùng để cấu hình thiết bị từ xa qua ThingsBoard Dashboard.
- `camera_id`: (int) ID nghiệp vụ của camera.
- `capture_interval_ms`: (int) Tần suất chụp ảnh (100ms - 3600s).
- `jpeg_quality`: (int) Chất lượng JPEG (4 - 63).
- `resolution`: (string/int) Độ phân giải (VGA, QVGA, HD, UXGA...).
- `telemetry_interval_ms`: (int) Tần suất gửi telemetry (5s - 3600s).
- `tl_red_ms`, `tl_yellow_ms`, `tl_green_ms`: (int) Thời gian đèn giao thông.
- `target_fw_version`: (string) Phiên bản firmware đích để kích hoạt OTA.
- `ota_url`: (string) URL tải firmware mới.
- `reboot`: (bool) Set true để khởi động lại.
- `factory_reset`: (bool) Set true để xóa NVS và restart.

### Client Attributes (Từ Device lên Server)
- `mac_address`: MAC định danh phần cứng.
- `device_model`: "PCB Cam AI S3".
- `fw_version`, `idf_ver`: Thông tin phiên bản phần mềm.
- `ip_address`, `stream_url`: Thông tin mạng và endpoint stream.
- `location`: Vị trí lắp đặt.
- `reset_reason`: Lý do khởi động lại gần nhất.

## 2. Telemetry (Dữ liệu định thời)

- `status`: "online" / "offline".
- `device_state`: "running", "ota", "error", "wifi_connecting".
- `cpu_temp`: Nhiệt độ chip ESP32.
- `free_heap`, `min_free_heap`: Trạng thái bộ nhớ.
- `wifi_rssi`, `wifi_disconnect_count`: Chất lượng kết nối WiFi.
- `uptime_s`: Thời gian chạy từ lúc boot.
- `Light_Mode`: Trạng thái đèn (RED, YELLOW, GREEN).
- `traffic_light_state`: Chi tiết trạng thái phase đèn.

## 3. Remote Procedure Calls (RPC)

| Method | Params | Mô tả |
| :--- | :--- | :--- |
| `setResolution` | `{"framesize": int}` | Đổi độ phân giải camera ngay lập tức. |
| `setQuality` | `{"quality": int}` | Đổi chất lượng ảnh. |
| `setInterval` | `{"interval_ms": int}` | Đổi tần suất chụp ảnh. |
| `reboot` | `{}` | Khởi động lại thiết bị. |
| `factoryReset` | `{}` | Xóa toàn bộ NVS và khởi động lại. |
| `reprovision` | `{}` | Xóa token hiện tại và đăng ký lại với TB. |
| `startOTA` | `{"url": string}` | Kích hoạt cập nhật firmware từ URL. |
| `getStatus` | `{}` | Lấy toàn bộ trạng thái runtime của thiết bị. |
| `getTrafficStatus`| `{}` | Lấy trạng thái chi tiết của đèn giao thông. |
| `setNormalMode` | `{}` | Chuyển đèn về chế độ chạy tự động. |
| `setEmergencyRed`| `{}` | Ép đèn sang màu ĐỎ (khẩn cấp). |
| `setEmergencyGreen`| `{}` | Ép đèn sang màu XANH (khẩn cấp). |
