# Bộ Tài Liệu Kỹ Thuật Hệ Thống (Backend & IoT)

Đây là bộ tài liệu chuẩn xác nhất về kiến trúc, cơ sở dữ liệu và quy trình vận hành của hệ thống Camera AI (bao gồm Backend, Database, Web và ThingsBoard Mapping).

## 1. Ưu tiên đọc cho người mới

1. [01_BACKEND_OVERVIEW.md](./01_BACKEND_OVERVIEW.md)
   Kiến trúc tổng thể của hệ thống, vai trò của từng lớp và luồng dữ liệu chuẩn.

2. [09_UNIFIED_CONFIG_SYNC.md](./09_UNIFIED_CONFIG_SYNC.md)
   **Quy tắc "Vàng" về cấu hình**: Nơi sửa đổi các thông số hạ tầng và quy trình đồng bộ tự động.

3. [02_BACKEND_API_V1.md](./02_BACKEND_API_V1.md)
   Danh mục các API Endpoint phục vụ cho giao diện Web và các dịch vụ ngoại vi.

4. [04_BACKEND_DATABASE.md](./04_BACKEND_DATABASE.md)
   Chi tiết về cấu trúc bảng Supabase/PostgreSQL, cơ chế định danh MAC và View tổng hợp.

5. [esp32_s3.md](./esp32_s3.md)
   Trạng thái Firmware hiện tại của thiết bị Camera đầu cuối.

## 2. Tài liệu hướng dẫn chuyên sâu

- [07_BACKEND_DEPLOYMENT.md](./07_BACKEND_DEPLOYMENT.md): Hướng dẫn triển khai thực tế trên Server/Hosting.
- [thingsboard/00_README.md](./thingsboard/00_README.md): Cách thức ánh xạ giữa ESP32 - ThingsBoard - Backend.
- [08_BACKEND_REFACTOR_ROADMAP.md](./08_BACKEND_REFACTOR_ROADMAP.md): Lộ trình nâng cấp và cải tiến hệ thống.

## 3. Trạng thái và Cam kết Hệ thống

Hệ thống đã được chuẩn hóa theo các tiêu chuẩn mới nhất:
- **Backend-Centric**: Backend là API trung gian duy nhất, bảo vệ thiết bị và cơ sở dữ liệu.
- **Dynamic Identification**: Sử dụng địa chỉ MAC làm neo định danh duy nhất (Anchor), không phụ thuộc IP.
- **Zero-CPU Stream**: Cơ chế Proxy luồng video MJPEG tối ưu nhất cho nhiều người xem cùng lúc.
- **Accented Vietnamese**: Toàn bộ giao diện người dùng, log hệ thống và tài liệu kỹ thuật đều sử dụng Tiếng Việt có dấu chuyên nghiệp.

---
**Thứ tự ưu tiên tham chiếu khi có mâu thuẫn:**
1. Code Backend & Database thực tế.
2. Bộ tài liệu chuẩn này (`docs/*.md`).
3. Các file cấu hình mẫu (`.env.sample`).
