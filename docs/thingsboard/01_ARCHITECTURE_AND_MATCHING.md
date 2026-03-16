# Kiến Trúc Và Quy Tắc Match

## 1. Kiến Trúc Hệ Thống

Hệ thống được thiết kế theo mô hình 4 lớp đảm bảo tính linh hoạt và khả năng mở rộng:

- **Thiết bị (ESP32-S3)**: Chụp ảnh, phát stream nội bộ và báo cáo trạng thái IoT.
- **ThingsBoard (IoT Layer)**: Quản lý định danh (Identity), cấu hình điều khiển (RPC) và cập nhật phần mềm (OTA).
- **Backend (Business Layer)**: Đồng bộ dữ liệu từ thiết bị và ThingsBoard, quản lý nghiệp vụ violations và proxy stream.
- **Web (Frontend Layer)**: Cung cấp giao diện dashboard cho người dùng cuối, tương tác hoàn toàn qua Backend API.

## 2. Các Lớp Định Danh

Hệ thống sử dụng bộ định danh sau để liên kết thiết bị:

- **`mac_address`**: **Định danh "cứng" (Hard Anchor)**. Dùng để xác định thiết bị vật lý không đổi, ngay cả khi `camera_id` hoặc tên thay đổi.
- **`camera_id`**: Định danh nghiệp vụ duy nhất. Một `camera_id` có thể được gán cho các `mac_address` khác nhau trong trường hợp thay thiết bị.
- **`tb_device_name`**: Định danh trên ThingsBoard (`cam-<MAC>`).
- **`device_name`**: Tên hiển thị (Ví dụ: `PCB Cam AI S3 001`).

## 3. Quy Tắc "Nguồn Sự Thật" (Source of Truth)

Để đảm bảo dữ liệu nhất quán, hệ thống tuân thủ quy tắc ưu tiên:

### Định danh và Tên Camera
1. **MAC Address**: Ưu tiên số 1 để tìm thiết bị đã tồn tại (Persistence).
2. `cameras.camera_name`: Tên do Admin đặt thủ công.
3. `cameras.tb_device_name`: Tên map từ ThingsBoard.
4. `camera_provisioning.device_name`: Tên firmware gửi lên (Dự phòng).

### Stream URL
1. `cameras.stream_url` (Manual override).
2. Cấu trúc động: `scheme://host:port/path` lấy từ dữ liệu Provisioning Sync cuối cùng.

## 4. Ý Nghĩa Thiết Kế

Mô hình này cho phép:
- Thay đổi thiết bị phần cứng nhanh chóng mà không làm mất lịch sử violations (qua `camera_id`).
- Xem stream từ bất kỳ đâu thông qua Backend Proxy mà không cần NAT port.
- Quản trị tập trung toàn bộ cấu hình IoT thông qua dashboard ThingsBoard.

---
*Ghi chú: Mọi luồng xử lý trên Backend đều tuân thủ quy tắc match MAC -> TB Name để tự động hóa việc đăng ký thiết bị mới.*
