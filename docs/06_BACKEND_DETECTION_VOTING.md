# Detect, Tracking Và OCR Voting

## Vai trò của tài liệu này

File này mô tả lớp AI/violation nếu hệ thống chạy theo nhánh xử lý ảnh nghiệp vụ.

## Trạng thái hiện tại

Trong repo hiện tại:

- web và backend đang ưu tiên camera stream động
- luồng detection/voting nên xem là lớp nghiệp vụ mở rộng hoặc legacy branch

## Nếu dùng lại

Mục tiêu của lớp này là:

- gom nhiều frame
- tracking object theo `camera_id`
- vote OCR để giảm sai
- chỉ tạo violation khi rule nghiệp vụ hợp lệ

## Điều kiện đúng chuẩn

Nếu bật lại nhánh này, nên chỉ tạo violation khi kết hợp đủ:

- zone
- stop line
- traffic light state
- OCR hợp lệ
- frame evidence hợp lệ

## Source of truth

- [08_BACKEND_REFACTOR_ROADMAP.md](./08_BACKEND_REFACTOR_ROADMAP.md)
