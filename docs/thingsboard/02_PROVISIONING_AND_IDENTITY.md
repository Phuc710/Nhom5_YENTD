# Provisioning Và Định Danh Thiết Bị

Firmware ESP32-S3 sử dụng cơ chế đăng ký kép (Dual Provisioning) để đảm bảo đồng bộ giữa lớp IoT (ThingsBoard) và lớp nghiệp vụ (Custom Backend).

## 1. Luồng Provisioning

### Bước 1: ThingsBoard Registration
Cần `DEFAULT_TB_PROVISIONING_KEY` và `DEFAULT_TB_PROVISIONING_SECRET` trong `platformio.ini`.
- ESP32 gọi HTTPS tới ThingsBoard API.
- ThingsBoard trả về `accessToken`.
- ESP32 lưu token vào NVS và khởi tạo MQTT client.

### Bước 2: Backend Synchronization
Sau khi có token, ESP32 gọi POST `/api/cameras/provision` tới Backend.
- Gửi toàn bộ thông tin: `camera_id`, `mac_address`, `access_token` (TB), `stream_url`, `location`, `fw_version`.
- Backend nhận và lưu vào bảng `camera_provisioning`.
- Backend cập nhật hoặc tạo mới entry trong bảng `cameras` để Web có thể hiển thị stream ngay lập tức.

## 2. Hệ Thống Định Danh (Identity)

Hệ thống khớp (match) thiết bị dựa trên bộ khóa sau:

| Khóa | Tên trong Code | Ý nghĩa |
| :--- | :--- | :--- |
| **Nghiệp vụ** | `camera_id` | Định danh camera trong hệ thống giám sát (Zone, Violation). |
| **Vật lý** | `mac_address` | Địa chỉ MAC duy nhất của chip ESP32. |
| **IoT Layer** | `tb_device_name` | Tên thiết bị trên ThingsBoard (thường là `cam-<MAC>`). |
| **Cấu hình** | `access_token` | Token ThingsBoard dùng để gửi/nhận MQTT. |
| **Hiển thị** | `device_name` | Tên gợi nhớ (ví dụ: "Cam-A123") sinh ngẫu nhiên hoặc từ firmware. |

## 3. Quy tắc "Nguồn Sự Thật" (Source of Truth)

1. **Stream URL**: Lấy từ bảng `cameras` (nếu có override) hoặc ghép từ thông tin IP/Port trong `camera_provisioning`.
2. **Device Info**: Ưu tiên dữ liệu mới nhất từ `camera_provisioning` gửi lên.
3. **Control**: Mọi lệnh điều khiển (RPC) từ Web sẽ qua Backend -> ThingsBoard (dùng `tb_device_name`).
