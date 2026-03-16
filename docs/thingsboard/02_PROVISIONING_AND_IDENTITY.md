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
| **Vật lý (Anchor)** | `mac_address` | **Khóa chính để nhận diện thiết bị vật lý**. |
| **Nghiệp vụ** | `camera_id` | Liên kết dữ liệu Vi phạm, Zone với thiết bị. |
| **IoT Identity** | `tb_device_name` | Tên thiết bị trên ThingsBoard (`cam-<MAC>`). |
| **Trạng thái** | `light_mode` | Trạng thái đèn (`red`, `green`, `yellow`, `off`). |
| **Phần mềm** | `idf_version` | Phiên bản ESP-IDF dùng để build firmware. |

## 3. Quy tắc "Khớp" Định Danh (Matching Logic)

1. **MAC First**: Khi nhận data, Backend tìm trong bảng `camera_provisioning` theo `mac_address` trước. Nếu thấy, lấy `camera_id` tương ứng.
2. **TB Match**: Nếu không thấy MAC, Backend tìm theo `tb_device_name`.
3. **Auto Mapping**: Backend tự động chuyển đổi các field từ firmware/ThingsBoard về chuẩn chung:
   - `Light_Mode` (TB) ➔ `light_mode` (Backend)
   - `idf_ver` (TB) ➔ `idf_version` (Backend)
   - Chuyển `RED`/`GREEN` ➔ `red`/`green` (lowercase).

---
*Ghi chú: Cơ chế này đảm bảo tính nhất quán dữ liệu ngay cả khi user thay đổi tên thiết bị trên ThingsBoard.*
