# 🚦 Traffic Monitor — System Architecture & API Docs

Hệ thống được chia làm 3 thành phần chính hoạt động độc lập nhưng giao tiếp chặt chẽ với nhau:
1. **API Backend (FastAPI)**: Chịu trách nhiệm xử lý data DB, AI Model (YOLO/OCR), Streaming và giao tiếp MQTT.
2. **Frontend Web (HTML/JS/CSS)**: Khách hàng/Admin truy cập qua trình duyệt.
3. **Desktop App (PyQt5)**: Ứng dụng quản trị local cho PC.

---

## 1. BACKEND ARCHITECTURE (`/backend`)

Cấu trúc chuẩn theo **Controller-Service-Repository** pattern:
- **`api/routes/` (Controllers)**: Nơi định nghĩa các endpoint HTTP (FastAPI routers).
- **`api/services/` (Services)**: Chứa business logic.
  - `alpr_service.py`: Giao tiếp với AI Models (YOLO Detector, EasyOCR).
  - `db_service.py`: Giao tiếp Supabase (PostgreSQL + Auth).
  - `mqtt_service.py`: Client kết nối Mosquitto MQTT, parse telemetry từ ESP32.
  - `stream_manager.py`: Mở luồng camera (OpenCV), xử lý frame và stream MJPEG.
  - `image_service.py`: Xử lý nén ảnh sang WebP và upload lên Supabase Storage.
- **`services/violation_engine.py`**: **Core Logic AI**, chứa State Machine phân tích xe vượt đèn đỏ dựa trên `TrackState` (was_before_line + in_zone).
- **`core/` / `utils/`**: Logger UVI chuẩn, load settings.

---

## 2. API ENDPOINTS (FASTAPI)

Base URL: `http://localhost:9000`

### 🌱 Tổng Quan & Health (Root)
| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | Trả về thông tin version và danh sách API. |
| `GET` | `/health` | (Tại `/api/health`) Kiểm tra GPU, Model state, DB Supabase và MQTT connect. |

### 📷 Camera Management (CRUD)
| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/cameras` | Lấy danh sách camera (DB: `camera_id`, `stream_url`, `location`...). |
| `POST` | `/cameras` | Thêm camera mới. |
| `PUT` | `/cameras/{id}` | Cập nhật URL, tọa độ cho camera. |
| `DELETE` | `/cameras/{id}` | Xóa camera. |
| `POST` | `/cameras/{id}/provision`| Đăng ký (provision) ESP32-S3 MAC Address. |

### 🚨 Quản lý Vi Phạm (Violations)
| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/violations` | Lấy danh sách vi phạm (có phân trang `limit`, `offset`, lọc theo biển số). |
| `GET` | `/violations/stats/daily`| Thống kê số vi phạm theo ngày. |
| `POST` | `/violations/with-images`| **Quan trọng**: Tạo vi phạm mới, upload payload (ảnh raw bytes multipart). Backend tự nén WebP, crop xe/biển số rồi lưu DB. |
| `POST` | `/violations/with-images/b64`| Tương tự trên nhưng dùng JSON/Base64 để tăng tốc I/O nội bộ. |
| `GET` | `/violations/snapshot/webp` | Lấy frame stream hiện tại dưới dạng WebP tĩnh cực nhanh. |

### 📹 Video Streaming
| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/stream/start` | Bật luồng camera truyền vào `source` (RTSP, Webcam `0`, HTTP MJPEG). |
| `POST` | `/stream/stop` | Tắt stream, giải phóng memory. |
| `GET` | `/stream/feed` | **Luồng live MJPEG** để nhúng vào tag `<img src="...">` của frontend. |
| `GET` | `/stream/status`| Trạng thái stream hiện tại đang connect hay không. |

### ⚡ MQTT / IoT Edge Control
Giao tiếp hai chiều với ESP32-CAM và Đèn giao thông.
| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/mqtt/status` | Xem MQTT Client connect chưa. |
| `POST` | `/mqtt/traffic-light/{id}` | Điều khiển đèn (Gửi state `RED`, `GREEN`, `YELLOW` cho ESP32). |
| `POST` | `/mqtt/camera/{id}/control`| Gửi lệnh (ví dụ: `restart`, `rotate_180`) cho ESP32-CAM. |
| `GET` | `/mqtt/telemetry` | Lấy cache thông số Cảm biến từ ESP32 (Ping, RAM, FrameDrop). |

### 🧠 Cấu Hình AI & Vùng ROI
*Các API này giúp frontend vẽ và lưu tọa độ khung xanh/kẻ vạch.*
| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/zones` | Lấy list vùng ROI của camera. |
| `POST` | `/zones` | Lưu tọa độ JSON array cho các zone. |
| `GET` | `/settings` | Lấy cấu hình ngưỡng phạt, Threshold AI. |

---

## 3. DESKTOP APP ARCHITECTURE (`/app`)

Kiến trúc PyQt5 hoạt động bằng cách quản lý đa luồng (Multi-threading) để giao diện không bị giật lag khi AI chạy.

* **Layout chính (`ui/main_window.py`)**: 
  * Dùng `QStackedWidget` để chuyển giữa panel.
* **Component lõi (`app/core/`)**:
  * `mqtt_client.py`: Thread chạy paho-mqtt ngầm liên tục nghe tín hiệu MQTT.
  * `stream_client.py`: OpenCV VideoCapture chạy trong thread riêng.
  * `detection_worker.py`: Thread AI Model.
* **Logic Vi phạm Desktop**: Desktop app không gọi REST API qua mạng HTTP mà gọi thẳng Python Object (`ViolationEngine.process_frame()`) -> sau đó DB service lưu thẳng lên Supabase. Chạy như vậy tiết kiệm overhead vòng loop.

---

## 💡 HƯỚNG DẪN MAINTAIN & UPDATE

1. **Thêm API mới**: 
   * Viết hàm ở `backend/api/services/db_service.py` trước.
   * Thêm Route trong thư mục `backend/api/routes`. Mọi service I/O (Database, Save Image) nhớ dùng phương pháp Non-Blocking (Wrap quanh `asyncio.to_thread()`).
   
2. **Sửa Logic Phạt AI (`Vượt Đèn Đỏ -> Gắn Biển Báo Mới`)**: 
   * Chỉnh file `backend/services/violation_engine.py` (Hàm `_evaluate_track`). Logic phát hiện vi phạm dựa trên chuỗi frame history.
   * Format chuẩn hoá logger đã quy hoạch ở `backend/utils/logger.py`.

3. **Chỉnh Web Frontend (`/frontend`)**:
   * API calls nằm tại `api.js` và `main.js`.
   * Luồng gọi: `Axios` / `Fetch` -> URL `/api/...` (Vào API Bridge tại `run_web.py` -> Route xuống Backend gốc)
