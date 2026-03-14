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

- gọi ThingsBoard trực tiếp
- tự ghép stream URL
- tự hardcode tên camera/model

## 2. Luồng camera trên web

### Danh sách camera

- đọc từ backend
- dùng `snapshot` để nhẹ hơn MJPEG live

### Chi tiết camera

- có nút `Connect`
- có `Disconnect`
- stream đi qua backend proxy
- góc phải trên hiển thị:
  - tên camera
  - vị trí
  - thời gian

### Overlay và metadata

Web nên hiển thị:

- `camera_name`
- `device_label`
- `location`
- `server_time`
- trạng thái online

## 3. Nguyên tắc dữ liệu

- web lấy `camera_name` đã chuẩn hóa từ API
- `stream_url` lấy từ API/backend
- nếu có `configured_stream_url`, coi đó là dữ liệu quản trị, không phải giá trị nên tự dựng ở client

## 4. Điều khiển thiết bị

Hiện web nên giữ tối thiểu:

- chỉnh metadata camera
- chỉnh zone
- factory reset qua backend

## 5. Source of truth

- [01_BACKEND_OVERVIEW.md](/C:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
- [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [04_BACKEND_DATABASE.md](/C:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
