# 08 - Config And Secrets

Hệ thống quản lý cấu hình thông qua 3 lớp chính:

1. **Build-time Defaults**: Các giá trị mặc định được định nghĩa trong `platformio.ini`.
2. **NVS Runtime Config**: Các thông số WiFi và Access Token được lưu bền vững trong bộ nhớ NVS của ESP32.
3. **ThingsBoard Shared Attributes**: Cho phép thay đổi cấu hình từ xa (Resolution, Interval) mà không cần nạp lại code.

## 1. Cấu Hình Build-time (Dành cho Dev)

Bạn có thể chỉnh sửa các hằng số mặc định tại:
- `platformio.ini`: Chứa URL backend, ThingsBoard provisioning key/secret.
- `include/app_config.h`: Định nghĩa cấu trúc dữ liệu lưu trong NVS.

---
## 2. Cấu Hình Runtime (NVS)

NVS (Non-volatile Storage) lưu giữ trạng thái thiết bị giữa các lần khởi động:
- **WiFi SSID/Pass**: Lưu sau khi cấu hình qua Captive Portal.
- **ThingsBoard Token**: Lưu sau khi Provisioning thành công.
- **Backend Sync State**: Trạng thái đồng bộ với Backend API.

---
## 3. Quản Lý Bí Mật (Secrets)

- **Nguyên tắc**: Tuyệt đối không commit các file mang thông tin nhạy cảm như `accessToken` thật của thiết bị.
- **platformio.ini.example**: Luôn duy trì file example sạch sẽ để hướng dẫn các thành viên khác cấu hình môi trường.
- **Environment Variables**: Ưu tiên sử dụng biến môi trường hoặc file `.env` nếu có tích hợp CI/CD.

---
## 4. Đồng Bộ Định Danh (Auto Sync)
Hệ thống sử dụng **Identity Chain chuẩn** để duy trì tính nhất quán dữ liệu:
**MAC Address (Anchor)** ➔ **camera_id (Business)** ➔ **tb_device_name (IoT Layer)**

Tất cả thông số runtime (`light_mode`, `idf_version`, `ip_address`, `fw_version`) sẽ được gửi tự động qua luồng **Provisioning Sync** và **Heartbeat**, giúp Backend luôn nắm bắt được trạng thái mới nhất của thiết bị mà không cần cấu hình bằng tay.

