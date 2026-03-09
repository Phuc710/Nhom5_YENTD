---
name: traffic-violation-project
description: Quy chuẩn thực thi cho đồ án giám sát vi phạm giao thông dùng frontend PHP, backend FastAPI, ESP32-S3, ThingsBoard MQTT và Supabase. Dùng skill này khi cần thiết kế, refactor, mở rộng hoặc đồng bộ toàn hệ thống; đặc biệt khi sửa web quản trị, cổng tra cứu biển số, API backend, schema dữ liệu, luồng detect vi phạm hoặc tài liệu dự án.
---

# Traffic Violation Project

## Tổng quan

Thực hiện thay đổi theo đúng kiến trúc của repo:

- `frontend` chạy trên hosting
- `backend` chạy trên laptop hoặc PC
- `ThingsBoard + MQTT` chạy trên laptop
- `Supabase` là cơ sở dữ liệu trung tâm
- `ESP32-S3-DevKitC-1` là thiết bị camera + đèn giao thông + nút vật lý

Đọc [`references/project-map.md`](references/project-map.md) trước khi sửa nhiều phần của hệ thống.

## Quy trình làm việc bắt buộc

1. Xác định thay đổi thuộc khu nào:
   - web quản trị
   - cổng tra cứu biển số
   - API backend `v1`
   - API test `v2-test`
   - pipeline detect / OCR / voting
   - schema Supabase
   - firmware ESP32

2. Nếu thay đổi backend hoặc API, đối chiếu ngay với:
   - [`references/project-map.md`](references/project-map.md)
   - [`../../docs/02_BACKEND_API_V1.md`](../../docs/02_BACKEND_API_V1.md)
   - [`../../docs/03_BACKEND_API_V2_TEST.md`](../../docs/03_BACKEND_API_V2_TEST.md)

3. Nếu thay đổi web, giữ nguyên nguyên tắc:
   - web chỉ dành cho cục cảnh sát và trung tâm giám sát
   - công dân là luồng mobile, không đưa vào web quản trị
   - không trộn logic test vào web vận hành

4. Nếu thay đổi phát hiện vi phạm, nhớ rằng mục tiêu đúng là:
   - `zone + stop_line + traffic_light_state`
   - không chỉ `buffer -> OCR vote -> finalize`

## Quy tắc triển khai

### Frontend

- Dùng PHP theo cấu trúc OOP tối thiểu với bootstrap, class hỗ trợ và layout chung.
- Tất cả page mới phải đi qua `frontend/bootstrap.php`.
- Dùng `Frontend\App\Core\Page` để khai báo title, active nav, assets và config client.

### Backend

- Giữ `v1` ổn định cho frontend đang dùng.
- Mọi API test mới đặt dưới `/api/v2-test`.
- Không thêm endpoint thử nghiệm vào `v1`.

### Database

- Không hard-code zone trong backend.
- `camera_id` là khóa nghiệp vụ xuyên suốt.
- `v2-test` không được ghi vào `violations`.

### Documentation

- Tên file docs dùng ASCII ổn định.
- Nội dung docs dùng tiếng Việt có dấu đầy đủ.
- Khi đổi luồng hệ thống, cập nhật docs backend chính trước.

## Tài liệu nên mở theo ngữ cảnh

- Backend tổng quan:
  [`../../docs/01_BACKEND_OVERVIEW.md`](../../docs/01_BACKEND_OVERVIEW.md)

- API chính:
  [`../../docs/02_BACKEND_API_V1.md`](../../docs/02_BACKEND_API_V1.md)

- API test:
  [`../../docs/03_BACKEND_API_V2_TEST.md`](../../docs/03_BACKEND_API_V2_TEST.md)

- Database:
  [`../../docs/04_BACKEND_DATABASE.md`](../../docs/04_BACKEND_DATABASE.md)

- Image pipeline:
  [`../../docs/05_BACKEND_IMAGE_PIPELINE.md`](../../docs/05_BACKEND_IMAGE_PIPELINE.md)

- Detection và voting:
  [`../../docs/06_BACKEND_DETECTION_VOTING.md`](../../docs/06_BACKEND_DETECTION_VOTING.md)

- Refactor roadmap:
  [`../../docs/08_BACKEND_REFACTOR_ROADMAP.md`](../../docs/08_BACKEND_REFACTOR_ROADMAP.md)

## Khi nào cần dừng và làm rõ

Dừng và làm rõ nếu gặp một trong các trường hợp sau:

- người dùng muốn đổi hợp đồng API `v1`
- thay đổi luồng mobile nhưng lại nhét vào web admin
- muốn tạo violation nhưng chưa chốt rule `zone + stop_line`
- phát hiện schema trong code khác schema trong `database/schema.sql`
