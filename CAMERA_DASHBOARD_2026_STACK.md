# CAMERA_DASHBOARD_2026_STACK

## 1) Kiến trúc tổng thể

Hệ thống hiện tại chạy theo mô hình local real-runtime:

- `FastAPI backend` (`server/app.py`) là trung tâm API + realtime bridge.
- `Frontend static` (`DEVELOPER/*.html, *.css, *.js`) được serve bởi backend.
- `AI service` (`server/ai_engine.py`) xử lý camera frame, OCR, tạo vi phạm thật.
- `MQTT broker` (Mosquitto) dùng cho heartbeat/event thiết bị.
- `SQLite` (`server/traffic_ai.db`) lưu dữ liệu nghiệp vụ.
- `Storage ảnh` tại `imge/` (đặc biệt `imge/violations/...`).

## 2) Thành phần chính

### Backend
- File chính: `server/app.py`
- Framework: FastAPI + SQLAlchemy
- Vai trò:
  - CRUD camera/violation
  - Nhận heartbeat thiết bị
  - Camera stream proxy (`/api/cameras/{id}/stream`)
  - MQTT subscriber bridge -> cập nhật DB + phát realtime SSE
  - Serve frontend + ảnh tĩnh

### Frontend
- Files chính: `DEVELOPER/main.html`, `DEVELOPER/main.js`, `DEVELOPER/main.css`, `DEVELOPER/login.*`
- Dữ liệu lấy từ API backend thật (không dùng hardcode fake list cho production path)
- Nhận realtime từ SSE endpoint `/api/realtime/events`

### MQTT
- Broker config: `server/mosquitto.conf`
- Listener:
  - `1883` (MQTT)
  - `9001` (MQTT over WebSocket)
- Backend subscribe:
  - `traffic/camera/+/status`
  - `traffic/camera/+/heartbeat`
  - `traffic/camera/+/violation`
  - `traffic/system/events`

### AI Service
- File: `server/ai_engine.py`
- Luồng:
  - Capture frame -> detect/OCR (`image_processor.py`)
  - Lưu ảnh thật vào `imge/violations/{camera_code}/YYYY/MM/DD/...`
  - Gửi vi phạm về backend qua `POST /api/violations`
  - Có publish MQTT violation event theo topic `traffic/camera/{camera_code}/violation`

### Database
- DB: `server/traffic_ai.db` (SQLite)
- Schema: `server/schema.sql`
- Bảng chính:
  - `cameras`
  - `violations`
  - `device_heartbeats`
  - `users`

### Storage
- Ảnh vi phạm thật: `imge/violations/...`
- Backend serve ảnh qua route: `/imge/{filename:path}`

## 3) Luồng dữ liệu chính

### Luồng camera
1. Frontend gọi `GET /api/cameras`.
2. Chọn camera -> gọi `GET /api/cameras/{id}/stream`.
3. Backend proxy stream HTTP/MJPEG từ `camera.stream_url` về frontend.

### Luồng heartbeat
1. Thiết bị/simulator publish MQTT heartbeat hoặc gọi `POST /api/devices/heartbeat`.
2. Backend ghi `device_heartbeats`, cập nhật `cameras.last_seen`, `cameras.status`.
3. Backend phát SSE event `camera_status_updated`.
4. Rule offline: camera quá timeout heartbeat được chuyển trạng thái offline trong logic CRUD backend.

### Luồng vi phạm
1. AI service detect vi phạm thật.
2. AI lưu ảnh full/vehicle/plate vào storage thật.
3. AI gửi payload tới `POST /api/violations`.
4. Backend ghi DB `violations` và phát SSE event `violation_created`.

### Luồng realtime
- Frontend mở SSE: `GET /api/realtime/events?token=...`
- Backend push event chính:
  - `camera_status_updated`
  - `violation_created`
  - `system_event`

## 4) API chính (đang dùng)

### Auth/health/bootstrap
- `POST /api/login`
- `GET /api/health`
- `GET /api/bootstrap`

### Cameras
- `GET /api/cameras`
- `GET /api/cameras/{camera_id}`
- `POST /api/cameras`
- `PUT /api/cameras/{camera_id}`
- `DELETE /api/cameras/{camera_id}`
- `GET /api/cameras/{camera_id}/status`
- `GET /api/cameras/{camera_id}/stream`

### Violations
- `GET /api/violations`
- `GET /api/violations/{violation_id}`
- `POST /api/violations`
- `GET /api/violations/latest`

### Devices/Realtime
- `POST /api/devices/heartbeat`
- `GET /api/device-status`
- `GET /api/realtime/events`

### Frontend serving
- `GET /`
- `GET /main`
- `GET /login`
- `GET /index`
- `GET /imge/{filename:path}`

## 5) MQTT topic chính

- `traffic/camera/{camera_code}/status`
- `traffic/camera/{camera_code}/heartbeat`
- `traffic/camera/{camera_code}/violation`
- `traffic/system/events`

## 6) Entrypoint chính

- Backend: `server/app.py`
- AI service: `server/ai_engine.py`
- MQTT broker start script: `server/start_mqtt.bat`
- Backend start script: `server/start_server.bat`
- AI start script: `server/start_ai.bat`
- Frontend open script: `server/start_frontend.bat`
- Full stack start script: `server/start_all.bat`
