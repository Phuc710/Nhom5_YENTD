# Lộ Trình Refactor Backend

## Trạng thái hiện tại

Các lớp đã được chuẩn hóa đáng kể:

- schema động
- tên camera động
- stream URL động
- backend proxy stream
- web dùng backend làm lớp duy nhất

## Ưu tiên tiếp theo

### Bước 1: giữ vững nguồn sự thật

Luôn ưu tiên:

1. [database/schema.sql](../database/schema.sql)
2. code backend hiện tại
3. docs gốc trong `docs/`

### Bước 2: dọn nhánh legacy

Nếu không còn dùng:

- upload legacy
- finalize legacy
- docs/hàm cũ không được gọi

thì nên đánh dấu hoặc xóa hẳn để repo đỡ nhiễu.

### Bước 3: nếu quay lại nhánh AI nghiệp vụ

Khi làm tiếp lớp violation:

- thêm rule engine cho `zone + stop_line + traffic_light_state`
- chuẩn hóa pipeline tracking/OCR voting
- tách rõ test pipeline với pipeline nghiệp vụ

### Bước 4: firmware provisioning sync

Nếu cần web hiện đúng tên/code name từ ESP32:

- cho firmware gọi `POST /api/cameras/provision`
- gửi `device_name`, `project_name`, `device_model`, `stream_*`

### Bước 5: production hardening

- timeout và retry cho stream proxy
- monitor ThingsBoard sync
- log chuẩn hóa
- dọn env/config còn dư

## Kết luận

Ưu tiên hiện tại của repo nên là:

- camera lên web mượt
- naming động
- stream động
- ít hardcode

Không nên refactor ngược về assumptions cũ nếu chưa thật sự cần.
