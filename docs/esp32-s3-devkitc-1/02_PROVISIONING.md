# 02 - ThingsBoard Provisioning

## Ghi chú chuẩn hóa

Hệ thống hỗ trợ đăng ký kép để đảm bảo đồng bộ hoàn toàn giữa ESP32 và hệ sinh thái:

1. **ThingsBoard Provisioning**: Cấp identity IoT và Access Token để quản trị thiết bị.
2. **Backend Sync**: Đăng ký camera vào hệ thống giám sát nghiệp vụ thông qua API `/provision`.

## Thông Tin Đồng Bộ (Slim Payload)

Khi thực hiện Provisioning Sync, thiết bị gửi bản tin JSON rút gọn lên Backend:

- `camera_id`: (int) ID nghiệp vụ của camera.
- `camera_name`: (string) Tên hiển thị của camera (Friendly Name).
- `tb_device_name`: (string) Tên định danh trên ThingsBoard.
- `mac_address`: (string) Địa chỉ MAC (Hard Identity).
- `ip_address`: (string) IP hiện tại của thiết bị.
- `stream_url`: (string) URL MJPEG đầy đủ để backend kéo stream.
- `location`: (string) Vị trí lắp đặt.

> [!NOTE]
> Các trường kỹ thuật như `access_token`, `fw_version`, `cpu_temp`... đã được chuyển hoàn toàn sang kênh **ThingsBoard MQTT** để tối ưu hóa Data Plane.

## Liên Kết Dữ Liệu
Dữ liệu này được Backend sử dụng để tự động ánh xạ Camera vào Dashboard mà không cần sự can thiệp thủ công từ quản trị viên.

---
*Đọc thêm tại: [Architecture & Matching](../thingsboard/01_ARCHITECTURE_AND_MATCHING.md)*
