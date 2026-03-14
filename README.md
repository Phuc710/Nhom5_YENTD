# Hệ thống giám sát vi phạm giao thông

Repo này mô tả hệ thống mô phỏng giám sát giao thông theo mô hình:

- `frontend` chạy trên hosting
- `backend` chạy trên laptop hoặc PC
- `ThingsBoard + MQTT` chạy trên laptop
- `Supabase` là cơ sở dữ liệu trung tâm
- `ESP32-S3-DevKitC-1` là thiết bị camera + đèn giao thông + nút vật lý

## Port chuẩn của repo

Để toàn bộ cấu hình map với nhau, repo này chốt một bộ cổng chuẩn:

- `ThingsBoard Web / Provisioning`: `9090`
- `ThingsBoard MQTT`: `1883`
- `Mosquitto MQTT`: `1888`
- `Backend FastAPI`: `8000`

## Mục tiêu nghiệp vụ

Hệ thống cần đáp ứng các mục tiêu sau:

- web xem được stream camera theo thời gian thực
- web cấu hình được zone theo từng camera
- khi đèn đỏ, xe đi vào vùng vi phạm thì backend tạo hồ sơ vi phạm
- hồ sơ vi phạm gồm ảnh toàn cảnh, ảnh crop biển số, biển số OCR, thời gian và camera
- mọi cấu hình phải động, không hard-code

## Logic đèn giao thông

### Chế độ bình thường

- chu kỳ `đỏ -> xanh -> vàng -> đỏ`
- thời gian từng pha có thể đổi từ backend hoặc ThingsBoard

### Chế độ khẩn cấp đỏ

- nhấn nút đỏ hoặc gọi `setEmergencyRed`
- hệ thống khóa ở đèn đỏ
- dừng chu kỳ và dừng đếm thời gian
- nhấn lại nút đỏ hoặc gọi `setNormalMode` để quay về bình thường

### Chế độ khẩn cấp xanh

- nhấn nút xanh hoặc gọi `setEmergencyGreen`
- hệ thống khóa ở đèn xanh
- dừng chu kỳ và dừng đếm thời gian
- nhấn lại nút xanh hoặc gọi `setNormalMode` để quay về bình thường

## Kiến trúc triển khai

```text
ESP32-S3-DevKitC-1
-> MQTT / RPC -> ThingsBoard trên laptop
-> HTTP provisioning sync + stream local -> Backend FastAPI trên laptop hoặc PC
-> Supabase PostgreSQL
-> Frontend PHP/JS trên hosting
```

## Trạng thái code hiện tại

Đã có:

- firmware hỗ trợ `normal`, `emergency_red`, `emergency_green`
- frontend có stream camera và zone editor
- backend có camera API, violation API, dashboard API
- schema Supabase có `cameras`, `camera_provisioning`, `detection_zones`, `violations`, `ocr_results`

Chưa đồng bộ hoàn toàn:

- backend chưa dùng `detection_zones` để kết luận vi phạm
- stats đang có hai namespace trùng vai trò
- `v2-test` mới được chốt ở mức tài liệu, chưa implement

## Phạm vi giao diện

- web là dashboard quản trị cho cục cảnh sát và trung tâm giám sát
- mobile là phần dành cho người dân, hiện mới dừng ở mức tài liệu mô tả

## Bộ tài liệu backend chuẩn

Tên file dùng ASCII để ổn định môi trường. Nội dung bên trong dùng tiếng Việt có dấu đầy đủ.

- [`docs/00_BACKEND_DOCS_INDEX.md`](/c:/Users/Phucc/Desktop/ytd/docs/00_BACKEND_DOCS_INDEX.md)
- [`docs/01_BACKEND_OVERVIEW.md`](/c:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
- [`docs/02_BACKEND_API_V1.md`](/c:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [`docs/03_BACKEND_API_V2_TEST.md`](/c:/Users/Phucc/Desktop/ytd/docs/03_BACKEND_API_V2_TEST.md)
- [`docs/04_BACKEND_DATABASE.md`](/c:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
- [`docs/06_BACKEND_DETECTION_VOTING.md`](/c:/Users/Phucc/Desktop/ytd/docs/06_BACKEND_DETECTION_VOTING.md)
- [`docs/07_BACKEND_DEPLOYMENT.md`](/c:/Users/Phucc/Desktop/ytd/docs/07_BACKEND_DEPLOYMENT.md)
- [`docs/08_BACKEND_REFACTOR_ROADMAP.md`](/c:/Users/Phucc/Desktop/ytd/docs/08_BACKEND_REFACTOR_ROADMAP.md)

## Bộ tài liệu ThingsBoard chuẩn

- [`docs/thingsboard/00_README.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/00_README.md)
- [`docs/thingsboard/01_ARCHITECTURE_AND_MATCHING.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/01_ARCHITECTURE_AND_MATCHING.md)
- [`docs/thingsboard/02_PROVISIONING_AND_IDENTITY.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/02_PROVISIONING_AND_IDENTITY.md)
- [`docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
- [`docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md)
- [`docs/thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md)
- [`docs/thingsboard/06_STANDARD_OPERATION_FLOWS.md`](/c:/Users/Phucc/Desktop/ytd/docs/thingsboard/06_STANDARD_OPERATION_FLOWS.md)

## Thứ tự sửa đồng bộ nên làm

1. chốt docs và hợp đồng API `v1`
2. dọn namespace stats bị trùng
3. tạo `v2-test` chỉ cho camera + detect model
4. thêm rule engine `zone + stop_line + traffic_light_state`
5. chuẩn hóa response schema
6. đồng bộ frontend theo backend mới
