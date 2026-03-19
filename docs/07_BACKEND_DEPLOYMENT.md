# Hướng Dẫn Triển Khai Hệ Thống (Deployment Guide)

Tài liệu này hướng dẫn cách triển khai hệ thống Camera AI trong thực tế:

- **Frontend**: Triển khai trên Web Hosting (PHP/Apache/Nginx).
- **Backend**: Chạy trên PC, Laptop hoặc Server chuyên dụng (FastAPI/Python).
- **Database**: Sử dụng Supabase hoặc PostgreSQL cục bộ.
- **ThingsBoard**: Lớp quản lý thiết bị (tùy chọn hoặc bắt buộc tùy cấu hình).

## 1. Thành phần chính

Để hệ thống vận hành, cần có các thành phần sau:
- Giao diện người dùng (Frontend PHP/JS).
- Bộ xử lý trung tâm (Backend FastAPI).
- Cơ sở dữ liệu (Supabase / PostgreSQL).
- Nền tảng IoT ThingsBoard (Điều phối thiết bị).
- Thiết bị đầu cuối (ESP32-S3 Camera).

## 2. Nguyên tắc triển khai cốt lõi

- **Tính độc lập**: Web chỉ giao tiếp trực tiếp với Backend qua API.
- **Tính tập trung**: Backend là lớp Proxy duy nhất cho luồng Stream và đồng bộ dữ liệu.
- **Tính linh hoạt**: Không viết chết (hardcode) tên miền hay URL stream. Mọi thông tin đều được lấy từ cấu hình động hoặc Database.

## 3. Cấu hình biến môi trường (.env)

### Backend
File: `backend/.env`
Các nhóm biến quan trọng:
- Thông tin kết nối Supabase (`SUPABASE_URL`, `SUPABASE_KEY`).
- Cấu hình Server (`HOST`, `PORT`, `PUBLIC_API_URL`).
- Cấu hình ThingsBoard và MQTT.
- Danh sách domain được phép truy cập (`CORS_ORIGINS`).

### Frontend
File: `frontend/.env`
- Nếu `API_URL` để trống, Frontend sẽ tự động sử dụng domain hiện tại làm gốc.
- Nếu Backend chạy trên một domain khác, cần điền địa chỉ chính xác của Backend vào đây.

## 4. Các mô hình triển khai thực tế

### Mô hình A: Cùng tên miền (Same Origin)
Ví dụ:
- Frontend: `https://camera-ai.top`
- Backend API: `https://camera-ai.top/api/...`
- **Ưu điểm**: Cấu hình đơn giản, không lo lắng về lỗi CORS hay vấn đề kết nối Real-time (SSE).
- **Cách làm**: Sử dụng Reverse Proxy để điều hướng các request `/api/` sang cổng của Backend.

### Mô hình B: Tên miền riêng biệt (Cross Origin)
Ví dụ:
- Frontend: `https://monitor.com`
- Backend: `https://api-backend.com`
- **Cần cấu hình**: Đặt `API_URL` ở Frontend và khai báo `CORS_ORIGINS` ở Backend để cho phép kết nối.

## 5. Lưu ý về luồng Stream MJPEG

Để giao diện Web có thể xem được camera từ xa:
1. Backend phải có khả năng kết nối tới `stream_url` của Camera (trong cùng mạng LAN hoặc qua VPN/Tunnel).
2. Frontend phải kết nối ổn định tới Backend.

**Quan trọng**: Nếu Frontend nằm trên Hosting công khai nhưng Backend chỉ có IP nội bộ (`192.168.x.x`), người dùng ngoài internet sẽ không thể xem được camera. Bạn cần có Public IP hoặc công cụ Tunnel (như Cloudflare Tunnel) cho Backend.

## 6. Cấu hình Real-time (SSE) qua Reverse Proxy

Nếu bạn sử dụng Nginx làm Proxy, hãy đảm bảo các thiết lập sau cho endpoint `/api/realtime/stream`:
- Tắt chế độ đệm (Proxy Buffering: `off`).
- Tăng thời gian chờ (Proxy Read Timeout).
- Sử dụng giao thức `HTTP/1.1`.

## 7. Kiểm tra sau khi triển khai

Sau khi setup, hãy kiểm tra các bước sau:
- Truy cập thành công trang sức khỏe: `/health`.
- Frontend lấy được danh sách camera từ: `/api/cameras`.
- Luồng Real-time nhận được dữ liệu (Bounding Boxes).
- Chức năng chụp ảnh (`snapshot`) và xem trực tiếp hoạt động bình thường trên giao diện Web.

---
Tài liệu tham khảo: [Tổng quan](./01_BACKEND_OVERVIEW.md) | [Cấu trúc Database](./04_BACKEND_DATABASE.md)
