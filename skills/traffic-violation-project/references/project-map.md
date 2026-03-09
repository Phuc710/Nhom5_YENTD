# Project map

## Kiến trúc chuẩn

- `frontend` trên hosting
- `backend` trên laptop hoặc PC
- `ThingsBoard + MQTT` trên laptop
- `Supabase` là nguồn dữ liệu trung tâm
- `ESP32-S3-DevKitC-1` là thiết bị camera + đèn giao thông + nút vật lý

## Web

Web chỉ dành cho khu quản trị:

### Khu quản trị

- `index.php`: trung tâm điều phối
- `cameras.php`: danh sách camera
- `camera.php`: chi tiết camera, stream, zone, setting
- `violations.php`: danh sách vi phạm
- `violation-detail.php`: hồ sơ vi phạm chi tiết

Phần người dân:

- không nằm trong web hiện tại
- chỉ được mô tả ở tài liệu mobile

## Frontend OOP

Các thành phần nền:

- `frontend/bootstrap.php`
- `frontend/app/Core/Page.php`
- `frontend/app/Support/Nav.php`

## Backend API

`v1` là API chính đang chạy.

Namespace hiện có:

- `/api/cameras`
- `/api/violations`
- `/api/upload`
- `/api/finalize`
- `/api/stats`

`v2-test` mới ở mức hợp đồng tài liệu, chưa implement.

## Điểm chưa hoàn tất trong backend

- chưa áp rule `detection_zones`
- chưa có rule `stop_line`
- chưa đồng bộ hoàn toàn namespace stats
- chưa implement `v2-test`
