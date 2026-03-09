# Triển khai backend

Tài liệu này ưu tiên mô hình bạn đang dùng:

- frontend trên hosting
- backend trên laptop hoặc PC
- ThingsBoard trên laptop

## 0. Port chuẩn đang chốt cho toàn repo

- `ThingsBoard Web / Provisioning`: `9090`
- `ThingsBoard MQTT`: `1883`
- `Mosquitto MQTT`: `1888`
- `Backend FastAPI`: `8000`

## 1. Yêu cầu môi trường

- Python 3.10+
- quyền đọc thư mục project
- kết nối được tới Supabase
- kết nối được tới ThingsBoard nếu dùng đồng bộ provisioning

## 2. Cấu hình backend

File chính:

- `backend/.env`

Các biến quan trọng:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`
- `HOST`
- `PORT`
- `DEBUG`
- `LOG_LEVEL`
- `UPLOAD_DIR`

## 3. Chạy backend local

Từ thư mục [`backend`](/c:/Users/Phucc/Desktop/ytd/backend):

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API docs:

- `http://localhost:8000/docs`

Health check:

- `http://localhost:8000/health`

## 4. Kết nối frontend hosting

Frontend chỉ gọi API qua `API_URL`.

File cần cấu hình:

- [`frontend/config.php`](/c:/Users/Phucc/Desktop/ytd/frontend/config.php)
- `frontend/.env` nếu có

Nguyên tắc:

- frontend không xử lý AI
- frontend không gọi Supabase trực tiếp cho nghiệp vụ backend
- frontend chỉ gọi backend

## 5. Expose backend ra ngoài mạng

Nếu frontend ở hosting công cộng thì backend trên laptop/PC phải có URL truy cập được từ internet hoặc VPN/tunnel nội bộ.

Bạn có thể dùng một trong các cách:

- reverse proxy trên máy chủ trung gian
- tunnel
- VPN
- public IP cố định

Tài liệu này không khóa cứng vào một giải pháp vì phụ thuộc hạ tầng bạn đang dùng.

## 6. Cấu trúc chạy production tối thiểu

```text
Frontend hosting
    -> gọi API_URL
Backend laptop/PC
    -> đọc/ghi Supabase
    -> nhận frame từ ESP32
ThingsBoard laptop
    -> MQTT / RPC / provisioning
ESP32
    -> stream + upload frame
```

## 7. Điều nên kiểm tra trước khi chạy thật

- backend lên được `/health`
- frontend gọi đúng `API_URL`
- backend ghi được `uploads`
- backend kết nối được Supabase
- ESP32 upload được `POST /api/upload`
- ESP32 gọi được `POST /api/finalize` khi đèn chuyển xanh
- ESP32 gọi được `POST /api/upload/heartbeat` khi không ở pha đỏ
- camera có `stream_url`

## 8. Điều không nên làm nữa

- không dùng launcher gộp frontend + backend trong cùng một file
- không mô tả frontend local là kiến trúc chuẩn nếu thực tế đang deploy hosting
