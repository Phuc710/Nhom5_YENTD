# Các Luồng Chuẩn End-To-End

## Luồng đang ưu tiên cho repo hiện tại

### Luồng A: camera xuất hiện trên web

1. Device được biết tới qua ThingsBoard sync hoặc provisioning sync.
2. Backend upsert `cameras` và `camera_provisioning`.
3. `view_camera_summary` trả dữ liệu tên/stream đã chuẩn hóa.
4. Frontend tự thấy camera mới.

### Luồng B: stream lên hosting

1. ESP32 phát stream cục bộ.
2. DB/backend dựng `stream_url` từ provisioning hoặc lấy override thủ công.
3. Web dùng backend proxy stream/snapshot.

### Luồng C: quản trị thiết bị

1. Web gọi backend.
2. Backend gọi ThingsBoard khi cần RPC như factory reset.

## Luồng cũ

Các flow boot/provisioning/MQTT/OTA chi tiết của firmware đời trước không còn nên được xem là flow mặc định cho toàn repo.

Đọc thêm:

- [01_BACKEND_OVERVIEW.md](/C:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
- [thingsboard/01_ARCHITECTURE_AND_MATCHING.md](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/01_ARCHITECTURE_AND_MATCHING.md)
