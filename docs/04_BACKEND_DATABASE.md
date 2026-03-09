# Cơ sở dữ liệu backend

File nguồn: [`database/schema.sql`](/c:/Users/Phucc/Desktop/ytd/database/schema.sql)

## 1. Vai trò của Supabase

Supabase là cơ sở dữ liệu trung tâm của hệ thống. Backend chịu trách nhiệm đọc và ghi dữ liệu nghiệp vụ vào đây.

## 2. Các bảng chính đang dùng

### `cameras`

Một bản ghi tương ứng một camera hoặc một thiết bị ESP32-S3-CAM.

Các cột quan trọng:

- `camera_id`
- `camera_name`
- `location`
- `latitude`
- `longitude`
- `stream_url`
- `description`
- `tb_device_name`
- `status`

### `camera_provisioning`

Lưu thông tin provision và heartbeat của thiết bị.

Các cột quan trọng:

- `camera_id`
- `tb_device_id`
- `access_token`
- `mac_address`
- `fw_version`
- `idf_version`
- `ip_address`
- `last_seen_at`
- `online`

### `detection_zones`

Lưu zone do frontend vẽ trên từng camera.

Các cột quan trọng:

- `camera_id`
- `zone_name`
- `x`
- `y`
- `width`
- `height`
- `zone_type`
- `active`

Giá trị `zone_type` hiện có:

- `detection`
- `stop_line`
- `roi`

### `violations`

Là bảng lưu vi phạm chính thức.

Các cột quan trọng:

- `camera_id`
- `license_plate`
- `confidence`
- `full_image_url`
- `cropped_plate_url`
- `violation_type`
- `traffic_light_state`
- `timestamp`
- `vote_count`
- `vote_percent`
- `total_frames`
- `track_id`
- `image_quality_score`
- `bbox_x`
- `bbox_y`
- `bbox_w`
- `bbox_h`
- `processing_time_ms`

### `ocr_results`

Lưu lịch sử OCR theo frame để debug và phân tích.

## 3. Các view chính

### `view_camera_summary`

Dùng cho:

- danh sách camera
- trạng thái online
- tổng số vi phạm

### `view_violations_full`

Dùng cho:

- danh sách vi phạm
- chi tiết vi phạm
- join thông tin camera và provisioning

### `view_daily_stats`

Dùng cho:

- dashboard theo ngày
- thống kê theo camera

## 4. Dữ liệu backend đang ghi vào đâu

### Camera

- ghi vào `cameras`
- cập nhật bằng `CameraRepository`

### Provisioning và heartbeat

- ghi vào `camera_provisioning`
- cập nhật `last_seen_at`

### Zone

- ghi vào `detection_zones`
- hiện dùng để lưu cấu hình
- chưa được pipeline detect dùng trọn vẹn

### Violation

- ghi vào `violations`
- ảnh thật lưu ở thư mục `uploads`, DB chỉ lưu URL

## 5. Những gì schema đã sẵn sàng nhưng backend chưa tận dụng hết

- zone detection theo từng camera
- stop line
- ROI
- lịch sử OCR chi tiết cho từng violation

## 6. Quy tắc cần giữ khi refactor

- `camera_id` là khóa nghiệp vụ xuyên suốt từ thiết bị đến frontend
- không hard-code zone trong backend
- vi phạm chỉ nên được tạo khi rule nghiệp vụ xác nhận hợp lệ
- `v2-test` không được ghi vào `violations`
