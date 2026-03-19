# Danh Mục Tài Liệu API (Backend API V1)

Tài liệu này chi tiết các Endpoint và giao thức kết nối (Contract API) của Backend.

## 1. Quy ước chung

- **Tiền tố (Prefix)**: `/api`
- **Công nghệ**: FastAPI (Python).
- **Nguyên tắc**: Giao diện Web chỉ gọi Backend. Backend chịu trách nhiệm điều phối dữ liệu từ ThingsBoard và ESP32.

## 2. Các Endpoint Hệ Thống

### `GET /`
Trả về thông tin phiên bản và metadata cơ bản của Backend.

### `GET /health`
Kiểm tra trạng thái hoạt động của hệ thống, bao gồm:
- Tình trạng kết nối Cơ sở dữ liệu (Supabase).
- Cấu hình CORS hiện tại.
- Trạng thái đồng bộ với ThingsBoard.

## 3. Quản lý Camera (Camera Endpoints)

### `GET /api/cameras`
Lấy danh sách toàn bộ camera từ View tổng hợp (`view_camera_summary`). Được sử dụng cho màn hình Dashboard và danh sách trực tiếp.

### `GET /api/cameras/{camera_id}`
Lấy thông tin chi tiết của một Camera cụ thể, bao gồm các thông số kỹ thuật (độ phân giải, WiFi SSID, phiên bản phần mềm) và cấu hình luồng stream.

### `PUT /api/cameras/{camera_id}`
Cập nhật thông tin quản trị cho Camera:
- Tên camera hiển thị.
- Vị trí lắp đặt.
- Ghi đè URL stream (`stream_url`).

### `DELETE /api/cameras/{camera_id}`
Gỡ bỏ Camera khỏi hệ thống quản lý.

### `GET /api/cameras/{camera_id}/stream`
Luồng Proxy MJPEG cho Video trực tiếp. Đảm bảo Web có thể xem được camera LAN từ internet thông qua Backend.

### `GET /api/cameras/{camera_id}/snapshot`
Lấy ảnh chụp tức thời (Snapshot) từ Camera.

### `GET /api/cameras/{camera_id}/live-view/sse`
**Server-Sent Events (SSE)**: Đẩy tọa độ các khung nhận diện AI (Bounding Boxes) về Web theo thời gian thực với độ trễ tối thiểu.

---

## 4. Cơ chế Đăng ký Thiết bị (Provisioning)

### `POST /api/cameras/provision`
Dành cho ESP32 hoặc Bridge gửi thông tin định danh ban đầu.
- **Hành vi**: Tự động tạo Camera mới hoặc cập nhật thông tin thiết bị cũ dựa trên **Địa chỉ MAC**.
- **Chuẩn hóa**: Tự động chuyển đổi các thuộc tính từ thiết bị về chuẩn nghiệp vụ của hệ thống.

## 5. Bảng Điều Khiển (Dashboard Endpoints)

### `GET /api/dashboard/overview`
Các số liệu tổng quan: Tổng số Camera, số lượng đang Online, tổng số vụ vi phạm trong ngày.

### `GET /api/dashboard/stats/hourly`
Thống kê số vụ vi phạm theo từng khung giờ trong ngày (định dạng phù hợp cho Chart.js).

### `GET /api/dashboard/stats/weekly`
Biểu đồ xu hướng vi phạm trong 7 ngày gần nhất.

## 6. Quản lý Vùng Nhận Diện (Zone Endpoints)

### `GET /api/cameras/{camera_id}/zones`
Lấy cấu hình các vùng nhận diện (Vạch dừng, Vùng vi phạm) của Camera.

### `PUT /api/cameras/{camera_id}/zones`
Cập nhật hoặc thiết lập mới các vùng tọa độ AI cho Camera.

## 7. Chuỗi Định Danh Tiêu Chuẩn (Identity Chain)

Hệ thống sử dụng các khóa định danh theo thứ tự ưu tiên để đảm bảo tính nhất quán:
1. **Địa chỉ MAC** (Khóa cứng - Quan trọng nhất).
2. **camera_id** (Mã định danh nghiệp vụ).
3. **tb_device_name** (Định danh trên hệ thống IoT ThingsBoard).

---
Tài liệu tham khảo: [Tổng quan hệ thống](./01_BACKEND_OVERVIEW.md) | [Cơ cấu Database](./04_BACKEND_DATABASE.md)
