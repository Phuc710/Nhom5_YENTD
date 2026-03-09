# Bộ tài liệu backend

Đây là bộ tài liệu backend chính thức của repo sau khi chuẩn hóa lại.

## Quy ước đặt tên

- Tên file dùng ASCII, viết hoa, có số thứ tự ở đầu.
- Nội dung bên trong dùng tiếng Việt có dấu đầy đủ.
- `v1` là API chính đang chạy theo code hiện tại.
- `v2-test` là nhánh tài liệu để test camera và model detect, không phải API nghiệp vụ chính.

## Danh sách tài liệu chính

1. [`01_BACKEND_OVERVIEW.md`](/c:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
   Mục tiêu hệ thống, kiến trúc triển khai, vai trò từng thành phần, luồng nghiệp vụ chuẩn.

2. [`02_BACKEND_API_V1.md`](/c:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
   Tài liệu API `v1` bám sát code thật đang có trong `backend/api`.

3. [`03_BACKEND_API_V2_TEST.md`](/c:/Users/Phucc/Desktop/ytd/docs/03_BACKEND_API_V2_TEST.md)
   Đề xuất API `v2-test` chỉ để test camera, frame và model detect/OCR, không ghi dữ liệu nghiệp vụ.

4. [`04_BACKEND_DATABASE.md`](/c:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
   Mô tả schema Supabase hiện có và cách backend sử dụng các bảng chính.

5. [`05_BACKEND_IMAGE_PIPELINE.md`](/c:/Users/Phucc/Desktop/ytd/docs/05_BACKEND_IMAGE_PIPELINE.md)
   Pipeline xử lý ảnh hiện tại và pipeline mục tiêu.

6. [`06_BACKEND_DETECTION_VOTING.md`](/c:/Users/Phucc/Desktop/ytd/docs/06_BACKEND_DETECTION_VOTING.md)
   Luồng detect, tracking, OCR voting, finalize violation và các điểm còn thiếu.

7. [`07_BACKEND_DEPLOYMENT.md`](/c:/Users/Phucc/Desktop/ytd/docs/07_BACKEND_DEPLOYMENT.md)
   Hướng dẫn triển khai backend trên laptop/PC hoặc máy chủ.

8. [`08_BACKEND_REFACTOR_ROADMAP.md`](/c:/Users/Phucc/Desktop/ytd/docs/08_BACKEND_REFACTOR_ROADMAP.md)
   Thứ tự refactor đồng bộ từ đầu đến cuối để tránh sửa lệch kiến trúc.

## Tài liệu liên quan nhưng không phải backend chính

- [`12_WEB_DASHBOARD.md`](/c:/Users/Phucc/Desktop/ytd/docs/12_WEB_DASHBOARD.md)
- [`13_MOBILE_APP.md`](/c:/Users/Phucc/Desktop/ytd/docs/13_MOBILE_APP.md)
- [`esp32_s3.md`](/c:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)
- Thư mục [`esp32-s3-devkitc-1`](/c:/Users/Phucc/Desktop/ytd/docs/esp32-s3-devkitc-1)
- Thư mục [`thingsboard`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard)

## Trạng thái hiện tại

Đã thống nhất:

- frontend chạy trên hosting
- backend chạy trên laptop/PC
- ThingsBoard và MQTT chạy trên laptop
- Supabase là cơ sở dữ liệu trung tâm
- ESP32-S3-DevKitC-1 là thiết bị camera + đèn giao thông + nút vật lý

Chưa đồng bộ hoàn toàn trong code:

- backend chưa áp rule `zone + stop_line + traffic_light_state` để kết luận vi phạm
- response API `v1` còn chưa thống nhất hoàn toàn về format
- namespace `/api/stats` và `/api/violations/stats/*` đang bị trùng vai trò
