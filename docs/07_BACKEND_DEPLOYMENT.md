# Triển Khai Backend

Tài liệu này mô tả cách deploy theo hướng hiện tại:

- frontend trên hosting
- backend trên PC/laptop hoặc server
- database trên Supabase/PostgreSQL
- ThingsBoard là lớp tùy chọn cho quản lý thiết bị

## 1. Thành phần chính

- Frontend PHP/JS
- Backend FastAPI
- Database PostgreSQL / Supabase
- ThingsBoard
- ESP32-S3 camera

## 2. Nguyên tắc triển khai

- Web chỉ gọi backend
- Backend mới là lớp proxy stream và đồng bộ dữ liệu
- Không hardcode domain trong frontend nếu cùng domain
- Không hardcode stream URL trong web nếu DB/view đã trả sẵn

## 3. Biến môi trường quan trọng

### Backend

File: [backend/.env](/C:/Users/Phucc/Desktop/ytd/backend/.env)

Nhóm quan trọng:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`
- `HOST`
- `PORT`
- `DEBUG`
- `LOG_LEVEL`
- `PUBLIC_API_URL`
- `THINGSBOARD_*`
- `CORS_ORIGINS`

### Frontend

File: [frontend/.env](/C:/Users/Phucc/Desktop/ytd/frontend/.env)

Nguyên tắc:

- nếu `API_URL` để trống, frontend tự lấy origin hiện tại
- nếu backend khác domain, đặt `API_URL` rõ ràng

## 3.1 Hai mô hình production nên dùng

### A. Cùng origin

Ví dụ:

- frontend: `https://app.example.com`
- backend API: `https://app.example.com/api/...`

Ưu điểm:

- không cần cấu hình `API_URL` khác domain
- SSE đơn giản hơn
- gần như không cần lo CORS

Cách làm:

- reverse proxy `/api/` từ web server sang backend
- dùng snippet [deploy/nginx/same-origin-api-proxy.conf.example](/C:/Users/Phucc/Desktop/ytd/deploy/nginx/same-origin-api-proxy.conf.example)
- frontend có thể để `API_URL` trống

### B. Tách domain

Ví dụ:

- frontend: `https://app.example.com`
- backend: `https://api.example.com`

Cần cấu hình:

- frontend `API_URL=https://api.example.com`
- backend `PUBLIC_API_URL=https://api.example.com`
- backend `CORS_ORIGINS=https://app.example.com`

Template:

- [deploy/nginx/api.example.com.conf.example](/C:/Users/Phucc/Desktop/ytd/deploy/nginx/api.example.com.conf.example)

## 4. Chạy local

Từ thư mục [backend](/C:/Users/Phucc/Desktop/ytd/backend):

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 5. Điều kiện để stream chạy trên hosting

Muốn web hosting xem được stream qua backend:

1. backend phải truy cập được `stream_url` của camera
2. frontend phải truy cập được backend

Nghĩa là:

- backend cùng LAN với camera, hoặc
- camera có route/tunnel/public access phù hợp, hoặc
- backend có VPN/tunnel tới mạng camera

Quan trọng:

- nếu frontend nằm trên hosting public nhưng backend chỉ là `http://192.168.x.x:8000`, trình duyệt ngoài internet sẽ không gọi được backend đó
- trong trường hợp này bạn phải có public domain hoặc reverse proxy/tunnel cho backend trước

## 5.1 SSE / realtime qua reverse proxy

Với endpoint `GET /api/realtime/stream`, reverse proxy phải:

- tắt buffer
- tăng `proxy_read_timeout`
- giữ `HTTP/1.1`

Hai file mẫu ở:

- [deploy/nginx/api.example.com.conf.example](/C:/Users/Phucc/Desktop/ytd/deploy/nginx/api.example.com.conf.example)
- [deploy/nginx/same-origin-api-proxy.conf.example](/C:/Users/Phucc/Desktop/ytd/deploy/nginx/same-origin-api-proxy.conf.example)

## 6. Kiểm tra sau deploy

- backend lên được `/health`
- frontend gọi được `/api/cameras`
- frontend nhận được `GET /api/realtime/stream`
- camera có `stream_url` trong `view_camera_summary`
- `GET /api/cameras/{id}/snapshot` hoạt động
- `GET /api/cameras/{id}/stream` hoạt động khi bấm `Connect`

## 7. Source of truth

- [01_BACKEND_OVERVIEW.md](/C:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
- [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [04_BACKEND_DATABASE.md](/C:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
