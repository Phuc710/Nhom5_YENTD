# Cơ Sở Dữ Liệu Backend

File nguồn: [database/schema.sql](../database/schema.sql)

## 1. Vai trò của DB

PostgreSQL/Supabase là nguồn dữ liệu chuẩn cho:

- camera registry
- provisioning động của ESP32-S3
- mapping ThingsBoard
- zone
- violation
- dữ liệu tổng hợp cho web

## 2. Bảng chính

### `cameras`

Lớp metadata do backend/web quản lý.

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

Ý nghĩa:

- `camera_name`: tên cấu hình tay hoặc override
- `stream_url`: stream override thủ công
- nếu hai field trên trống hoặc chỉ là placeholder, hệ thống sẽ lấy dữ liệu động từ provisioning

### `camera_provisioning`

Lớp dữ liệu động từ ESP32-S3 hoặc ThingsBoard sync.

Các cột quan trọng:

- `tb_device_id`
- `tb_device_name`
- `device_name`
- `project_name`
- `device_model`
- `wifi_ssid`
- `resolution`
- `access_token`
- `mac_address`
- `fw_version`
- `idf_version`
- `stream_scheme`
- `stream_host`
- `stream_port` / `stream_path`: Các thành phần để xây dựng URL stream động.
- `stream_snapshot_path`
- `ip_address`: IP hiện tại trong mạng nội bộ.
- `light_mode`: Trạng thái đèn (`red`, `green`, `yellow`, `off`).
- `last_seen_at`: Thời điểm cuối cùng thiết bị gửi tín hiệu.
- `last_boot_at`
- `online`: Trạng thái kết nối (được cập nhật qua Heartbeat).
- `extra_attributes` (JSONB): Lưu trữ các thuộc tính linh hoạt khác (phiên bản SDK, thông tin chip...).

Ý nghĩa:

- `device_name` và `project_name` giúp web/backend hiển thị đúng tên từ thiết bị
- `stream_*` cho phép dựng stream động mà không hardcode `http://<ip>:81/stream`
- `extra_attributes` là vùng mở rộng để scale về sau

### 2.3 Bảng `detection_zones`

Cấu hình các vùng nhận diện cho từng camera: Lưu cấu hình zone theo camera:

- Vùng vi phạm (`detection`).
- Vạch dừng (`stop_line`).
- Vùng AI ROI (`roi`).

### 2.4 Bảng `violations`

Lưu trữ hồ sơ vi phạm: Lưu vi phạm đã chốt:

- `full_image_url`: Đường dẫn ảnh toàn cảnh khi vi phạm.
- `cropped_plate_url`: Đường dẫn ảnh cắt biển số xe.
- `license_plate`: Biển số xe nhận diện được.
- `confidence`: Độ tin cậy của thuật toán AI.
- thông tin bbox
- thời gian
- tracking/voting metadata
- `violation_type`: Loại vi phạm (ví dụ: Vượt đèn đỏ).

### 2.5 Bảng `ocr_results`

Lưu lịch sử OCR theo frame để debug.

## 3. Cơ chế URL Stream động

Hệ thống tự động xây dựng `stream_url` nếu không có cấu hình thủ công:
1. Lấy thông tin từ `latest_provisioning`.
2. Hợp nhất: `<scheme>://<host>:<port><path>`.
3. Kết quả thường là: `http://192.168.1.50:81/stream`.

Cơ chế này giúp hệ thống hoạt động ổn định ngay cả khi camera thay đổi địa chỉ IP.

Hàm chuẩn hóa trong DB:

### `fn_camera_display_name`

Dùng để tính tên hiển thị động theo thứ tự:

1. `cameras.camera_name`
2. `cameras.tb_device_name`
3. `camera_provisioning.device_name`
4. `camera_provisioning.project_name`
5. `camera_provisioning.tb_device_name`
6. fallback `Camera 00x`

### `fn_stream_url`

Dùng để tính `stream_url` động theo thứ tự:

1. `cameras.stream_url`
2. `stream_scheme + stream_host/ip_address + stream_port + stream_path`

## 4. Đồng Bộ Định Danh (Auto Sync)

Hệ thống sử dụng **Identity Chain chuẩn** để đồng bộ:
**MAC Address** ➔ **camera_id** ➔ **tb_device_name**

Mọi thông số runtime (`light_mode`, `idf_version`, `ip_address`, `fw_version`) được gửi tự động qua luồng **Provisioning Sync** và **Heartbeat** để Backend cập nhật trạng thái "Live" liên tục.

## 5. View tổng hợp: `view_camera_summary`

Đây là view chính mà Frontend và Backend sử dụng để lấy trạng thái camera tổng thể. Nó tự động thực hiện các logic:
- Ánh xạ tên hiển thị chuyên nghiệp.
- Kiểm tra trạng thái "sống" của camera (Online nếu có heartbeat trong vòng 60 giây).
- Ghép URL stream hiệu dụng theo độ ưu tiên.

View này đã trả sẵn:

- `camera_name` đã chuẩn hóa
- `stream_url` đã chuẩn hóa
- `configured_camera_name`
- `configured_stream_url`
- `device_name`
- `project_name`
- `device_model`
- `wifi_ssid`
- `resolution`
- `stream_snapshot_path`

### `view_violations_full`

Join violation với camera + provisioning để web đọc một lần là đủ.

### `view_daily_stats`

Thống kê theo ngày cho dashboard.

## 6. Index và scale

Schema hiện có index cho:

- `camera_id`
- `tb_device_name`
- `mac_address`
- `online + last_seen_at`
- `violations.timestamp`
- `violations.camera_id`
- `violations.track_id`

Mục tiêu là:

- camera list nhanh
- ThingsBoard sync nhanh
- dashboard nhanh
- truy vấn vi phạm gần nhất nhanh

## 6. Quy tắc sử dụng

- `camera_id` là khóa nghiệp vụ xuyên suốt.
- Không hardcode tên camera trong app nếu DB/view đã trả tên chuẩn hóa.
- Không hardcode stream URL nếu DB/view đã trả `stream_url`.
- Chỉ dùng `configured_stream_url` khi cần phân biệt stream override tay với stream động.

## 7. Ghi chú migration

`schema.sql` hiện viết theo kiểu idempotent:

- `CREATE TABLE IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- `DROP POLICY IF EXISTS`
- `DROP TRIGGER IF EXISTS`

Nghĩa là file này dùng được cho cả:

- tạo DB mới
- nâng cấp DB cũ

Nếu có mâu thuẫn giữa doc và DB thật, ưu tiên [database/schema.sql](../database/schema.sql).
