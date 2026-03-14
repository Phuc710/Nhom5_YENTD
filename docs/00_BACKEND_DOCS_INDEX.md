# Bộ Tài Liệu Backend

Đây là bộ tài liệu gốc cho phần `backend + database + web + ThingsBoard mapping` của repo.

## Ưu tiên đọc

1. [01_BACKEND_OVERVIEW.md](/C:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
   Kiến trúc hiện tại của toàn hệ thống và vai trò từng lớp.

2. [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
   Contract API đang bám sát code backend hiện tại.

3. [04_BACKEND_DATABASE.md](/C:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
   Schema Supabase/PostgreSQL hiện tại, gồm naming động và stream động.

4. [thingsboard/00_README.md](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/00_README.md)
   Lớp ThingsBoard và cách match `ESP32-S3 <-> ThingsBoard <-> Backend <-> Web`.

5. [esp32_s3.md](/C:/Users/Phucc/Desktop/ytd/docs/esp32_s3.md)
   Trạng thái firmware ESP32-S3 hiện tại trong repo.

## Tài liệu bổ trợ

- [03_BACKEND_API_V2_TEST.md](/C:/Users/Phucc/Desktop/ytd/docs/03_BACKEND_API_V2_TEST.md)
- [06_BACKEND_DETECTION_VOTING.md](/C:/Users/Phucc/Desktop/ytd/docs/06_BACKEND_DETECTION_VOTING.md)
- [07_BACKEND_DEPLOYMENT.md](/C:/Users/Phucc/Desktop/ytd/docs/07_BACKEND_DEPLOYMENT.md)
- [08_BACKEND_REFACTOR_ROADMAP.md](/C:/Users/Phucc/Desktop/ytd/docs/08_BACKEND_REFACTOR_ROADMAP.md)
- [12_WEB_DASHBOARD.md](/C:/Users/Phucc/Desktop/ytd/docs/12_WEB_DASHBOARD.md)
- [13_MOBILE_APP.md](/C:/Users/Phucc/Desktop/ytd/docs/13_MOBILE_APP.md)

## Trạng thái hiện tại

Đã thống nhất:

- Backend là API trung gian duy nhất cho web.
- Database là nguồn dữ liệu chuẩn cho camera, provisioning, zone và violation.
- `stream_url` có thể cấu hình tay ở bảng `cameras`, hoặc được DB/backend tự dựng động từ provisioning.
- Tên camera hiển thị không nên hardcode ở frontend/backend nữa.
- ThingsBoard là lớp điều phối thiết bị và đồng bộ danh tính, không phải nơi hiển thị nghiệp vụ cho web.

Lưu ý:

- Một số tài liệu chi tiết cũ trong thư mục `docs/esp32-s3-devkitc-1` và `docs/thingsboard` vẫn còn giá trị tham khảo lịch sử, nhưng khi mâu thuẫn thì ưu tiên:
  1. [database/schema.sql](/C:/Users/Phucc/Desktop/ytd/database/schema.sql)
  2. code backend hiện tại
  3. bộ docs gốc này
