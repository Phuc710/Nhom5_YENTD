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

### Frontend

File: [frontend/.env](/C:/Users/Phucc/Desktop/ytd/frontend/.env)

Nguyên tắc:

- nếu `API_URL` để trống, frontend tự lấy origin hiện tại
- nếu backend khác domain, đặt `API_URL` rõ ràng

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

## 6. Kiểm tra sau deploy

- backend lên được `/health`
- frontend gọi được `/api/cameras`
- camera có `stream_url` trong `view_camera_summary`
- `GET /api/cameras/{id}/snapshot` hoạt động
- `GET /api/cameras/{id}/stream` hoạt động khi bấm `Connect`

## 7. Source of truth

- [01_BACKEND_OVERVIEW.md](/C:/Users/Phucc/Desktop/ytd/docs/01_BACKEND_OVERVIEW.md)
- [02_BACKEND_API_V1.md](/C:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [04_BACKEND_DATABASE.md](/C:/Users/Phucc/Desktop/ytd/docs/04_BACKEND_DATABASE.md)
