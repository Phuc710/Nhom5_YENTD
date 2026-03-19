# Web Dashboard

Tài liệu này mô tả web theo trạng thái hiện tại.

## 1. Vai trò của web

Web là giao diện quản trị và giám sát:

- danh sách camera
- chi tiết camera
- stream
- zone
- violations

Web không nên:

- gọi ThingsBoard trực tiếp qua HTTP
- tự ghép stream URL (Luôn phải đi qua Backend Multiplex Proxy)
- tự hardcode tên camera/model

## 2. Kiến trúc mã nguồn Frontend (Grok UI / OOP)

Web Frontend hiện đã được thiết kế lại hoàn toàn theo nguyên lý **OOP (Hướng đối tượng)**:

1. **`UIController` (Base Class)**: Lõi xử lý tương tác DOM (Toast, Loading, Text/HTML update).
2. **`CameraController` / `AnalyticsController`**: Kế thừa `UIController` để tách biệt Logic nghiệp vụ của từng trang. (Chart.js cho Analytics, MJPEG Stream cho Camera Detail).
3. **`RealtimeService`**: Một class Singleton kết nối **WebSockets** trực tiếp đến môi trường viễn thông để cập nhật biểu đồ mà không cần tải lại trang.
4. **`CameraService` / `AuthService`**: Client độc lập chuyên Request dữ liệu tới Backend REST API.
5. **Global Config `APP_CONFIG`**: Mọi Endpoint WebSockets, Server API được tiêm `window.APP_CONFIG` thống nhất bằng PHP.

- **Giao diện Grok UI**: Tuân thủ chuẩn UI công nghệ cao với Font chữ Mono, tông màu siêu tối sắc nét.

## 3. Luồng camera trên web

### Danh sách camera

- đọc từ backend
- dùng `snapshot` để nhẹ hơn MJPEG live

### Chi tiết camera

- có nút Hành động (`Connect`, `OTA`, `Reboot`, `Factory Reset`, `Traffic Light`)
- stream đi qua Backend Proxy theo cơ chế Multi-channel (Pub/Sub RAM Server - Tốc độ cao 30FPS+)
- góc phải trên hiển thị:
  - Tên camera (Chuẩn hóa)
  - Vị trí / Identity
  - Dữ liệu Telemetry Real-time (Pin, Nhiệt độ, RAM)

### Overlay và metadata (AI Bounding Boxes)

Web sử dụng **Server-Sent Events (SSE)** để lắng nghe vị trí phát hiện xe (Vi phạm) hoặc Bounding Box tĩnh một cách siêu tốc mà không làm giật lag Video (Zero-polling Interval). Khi AI tìm thấy xe vi phạm, ô vuông màu cam tự dán đè khớp 100% tỉ lệ ảnh video thực tế bằng kỹ thuật CSS Shrink-wrap.

Hiển thị:

- `camera_name`
- `device_label`
- `location`
- `server_time`
- trạng thái online

## 3. Nguyên tắc dữ liệu

- web lấy `camera_name` đã chuẩn hóa từ API
- `stream_url` lấy từ API/backend
- nếu có `configured_stream_url`, coi đó là dữ liệu quản trị, không phải giá trị nên tự dựng ở client

## 5. Điều khiển thiết bị

Web Frontend giữ vai trò giao tiếp **One-way** đến Backend:

- chỉnh metadata camera định danh
- tùy chỉnh bounding zone AI
- gửi lệnh OTA / Factory Reset / Reboot qua Backend
- Thao tác đèn giao thông ảo cho AI học.

## 6. Source of truth

- [01_BACKEND_OVERVIEW.md](./01_BACKEND_OVERVIEW.md)
- [02_BACKEND_API_V1.md](./02_BACKEND_API_V1.md)
- [04_BACKEND_DATABASE.md](./04_BACKEND_DATABASE.md)
