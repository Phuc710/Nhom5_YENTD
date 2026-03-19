# Các Luồng Chuẩn End-To-End

## Các Luồng Hoạt Động Chính

### 1. Luồng Camera Xuất Hiện Trên Web
1. Thiết bị boot và tự động Provisioning với ThingsBoard (nếu cần).
2. Thiết bị gửi thông tin `Provisioning Sync` lên Backend API.
3. Backend tự động map thiết bị vào danh sách Camera dựa trên MAC/camera_id.
4. Web Dashboard hiển thị camera mới với đầy đủ thông tin stream/trạng thái.

### 2. Luồng Xem Video (Stream Proxy)
1. ESP32 phát stream tại mạng cục bộ.
2. Backend đóng vai trò Proxy/Relay stream thông qua API `/stream`.
3. Web Dashboard hiển thị video mà không cần NAT port hay cấu hình IP tĩnh cho camera.

### 3. Luồng Quản Trị & Điều Khiển
1. Người dùng thay đổi cấu hình (Resolution, Quality) trên Web.
2. Web gọi API Backend.
3. Backend cập nhật Shared Attributes tương ứng trên ThingsBoard.
4. ESP32 nhận thay đổi qua MQTT và áp dụng ngay lập tức vào phần cứng.

Đọc thêm:

- [01_BACKEND_OVERVIEW.md](../01_BACKEND_OVERVIEW.md)
- [01_ARCHITECTURE_AND_MATCHING.md](./01_ARCHITECTURE_AND_MATCHING.md)
