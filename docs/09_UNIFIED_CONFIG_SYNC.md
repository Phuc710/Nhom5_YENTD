# Cấu Hình Đồng Bộ Toàn Hệ Thống

Tài liệu này chốt một lần cho rõ các quy tắc cấu hình:

- Sửa cấu hình ở đâu?
- Các giá trị mặc định là gì?
- Đâu là "Source of Truth" (Nguồn chân lý)?
- Cách thức đồng bộ giữa Backend, ThingsBoard, MQTT, ESP32-S3 và Frontend.

## 1. Mục tiêu

Hệ thống được chia làm 2 nhóm dữ liệu chính:

1.  **Cấu hình hạ tầng (Infrastructure Config)**
    Ví dụ:
    - URL của Backend.
    - URL của ThingsBoard.
    - Thông tin MQTT (host/port).
    - Provisioning key/secret.
    - API URL dành cho Frontend.
    - Các giá trị mặc định khi build cho ESP32-S3.

2.  **Dữ liệu nghiệp vụ và Runtime**
    Ví dụ:
    - Tên camera (`camera_name`).
    - URL luồng stream (`stream_url`) hiệu dụng cho Web.
    - Các vùng nhận diện (Zones).
    - Hồ sơ vi phạm (Violations).
    - Trạng thái Online/Offline.
    - Thời điểm nhìn thấy cuối cùng (`last_seen_at`).
    - Địa chỉ IP, chế độ đèn (`light_mode`).

Hai nhóm này có nguồn quản lý (Source of Truth) khác nhau.

## 2. Nguồn Quản Lý Chuẩn (Source Of Truth)

### 2.1 Cấu hình hạ tầng

**File `backend/.env` la noi chinh sua duy nhat.**

Cho all-local, chi sua dung 1 dong:

```env
LOCAL_LAN_IP=192.168.1.7
```

Cac bien local nhu `THINGSBOARD_URL`, `MQTT_TB_HOST`, `MQTT_HOST`, `PUBLIC_API_URL`, `CORS_ORIGINS` co the de trong de backend tu suy ra theo `LOCAL_LAN_IP`.

`ESP_CAMERA_ID` va `ESP_STATIC_IP` chi dung de sinh default cho firmware ESP32-S3. Backend khong dung hai gia tri nay de match camera; backend match theo `MAC + tb_device_name`.

Từ file này, hệ thống sẽ tự động đồng bộ (sync) ra các file sau:

- `frontend/.env`
- `esp32-s3-devkitc-1/platformio.ini`

Script thực hiện đồng bộ:

```bat
venv\Scripts\python.exe backend\scripts\sync_local_config.py
```

Hoặc chỉ cần chạy file khởi động hệ thống:

```bat
start_system.bat
```

Vì file này đã được tích hợp sẵn lệnh gọi sync trước khi khởi động Backend và giao diện Web.

### 2.2 Dữ liệu nghiệp vụ camera

**Cơ sở dữ liệu (Database) là nguồn chân lý cho Web và Backend.**

Cụ thể:

- Bảng `cameras`: Metadata do quản trị viên quản lý.
- Bảng `camera_provisioning`: Thông tin provisioning, heartbeat và runtime từ ESP32/ThingsBoard.
- Bảng `detection_zones`: Các vùng nhận diện.
- Bảng `violations`: Hồ sơ các vụ vi phạm.
- `view_camera_summary`: View tổng hợp chuẩn để Frontend truy vấn.

**Lưu ý quan trọng:**

- File `.env` KHÔNG phải là nơi lưu danh sách camera, khu vực hay vi phạm.
- Frontend không tự hardcode (viết chết) URL stream hay tên camera mà phải đọc qua API của Backend.

### 2.3 Cấu hình runtime trên ESP32

ESP32 có 3 lớp ưu tiên cấu hình:

1.  **NVS Runtime Config**: WiFi đã lưu, token đã provision, vị trí/ID camera đã lưu trong bộ nhớ Flash.
2.  **Build Defaults**: Các giá trị mặc định từ `platformio.ini` lúc nạp code.
3.  **Fallback**: Các giá trị được lập trình sẵn (hard-code) trong Firmware.

Quy tắc:

- `platformio.ini` chỉ cung cấp giá trị mặc định khi khởi động lần đầu.
- Sau khi ESP32 đã lưu vào NVS, giá trị trong NVS sẽ có ưu tiên cao nhất.
- Chỉ khi thực hiện Factory Reset (xóa NVS), thiết bị mới quay về giá trị trong `platformio.ini`.

## 3. Thứ Tự Ưu Tiên Chuan

### 3.1 URL API cho Frontend

Frontend hiện tại ưu tiên theo thứ tự:

1.  `FRONTEND_API_MODE=same_origin` -> Frontend gọi trực tiếp `/api`.
2.  `PUBLIC_API_URL` -> Backend public domain/IP.
3.  `API_URL` trong `frontend/.env` sinh tự động.
4.  Mặc định (Fallback): `http://<host-hiện-tại>:8000`.

Ý nghĩa:

- Local thường để `FRONTEND_API_MODE=direct`.
- Hosting production chuẩn nhất để `FRONTEND_API_MODE=same_origin`.
- Không sửa tay `frontend/.env` trong flow chuẩn.

### 3.2 URL Stream hiệu dụng cho Camera

Backend ưu tiên theo thứ tự:

1.  `cameras.stream_url` (nếu quản trị viên thiết lập thủ công).
2.  Thông tin stream động từ Runtime (Provisioning/Heartbeat): `scheme`, `host`, `port`, `path`.

### 3.3 Tên Camera hiển thị

Backend ưu tiên theo thứ tự:

1.  `cameras.camera_name` (tên đặt trong DB).
2.  `device_name` từ thiết bị.
3.  `project_name` hoặc `tb_device_name`.
4.  Mặc định: `Camera 00x`.

### 3.4 Định danh thiết bị (Device Identity)

Ưu tiên đối soát thiết bị dựa trên:

1.  `mac_address` (Địa chỉ MAC - quan trọng nhất).
2.  `camera_id`.
3.  `tb_device_name`.

Địa chỉ MAC là định danh duy nhất (anchor) để tránh bị nhảy camera khi thiết bị khởi động lại hoặc thực hiện lại quy trình provision.

## 4. Các File Chính Và Vai Trò

### 4.1 `backend/.env`

Đây là file quan trọng nhất để sửa các thông số:
- Kết nối Supabase và ThingsBoard.
- Cấu hình MQTT.
- URL công khai của Backend và thiết lập CORS.
- Cấu hình các mô hình AI (ML settings).
- Các thông số đồng bộ cho Frontend và ESP32.

### 4.2 `frontend/.env`

File này được sinh ra tự động, dùng để cung cấp:

- `FRONTEND_API_MODE`
- `API_URL`

cho Frontend (PHP/JS).

Không nên sửa thủ công. Hãy coi nó là artifact sinh ra từ `backend/.env`.

### 4.3 `esp32-s3-devkitc-1/platformio.ini`

Được đồng bộ từ `backend/.env`. Chứa các giá trị mặc định về URL Backend, ThingsBoard, MQTT và các thông số thiết bị ban đầu.

## 5. Luồng Đồng Bộ Toàn Hệ Thống

### 5.1 Luồng cấu hình phẳng

```text
backend/.env
   -> sync_local_config.py
      -> frontend/.env
      -> esp32-s3-devkitc-1/platformio.ini
```

### 5.2 Luồng Runtime thiết bị

```text
ESP32 Khởi động
  -> Tải cấu hình từ NVS (hoặc mặc định từ platformio.ini)
  -> Kết nối WiFi
  -> Kết nối ThingsBoard MQTT
  -> Gửi yêu cầu Provision và Heartbeat định kỳ tới Backend
Backend
  -> Cập nhật dữ liệu vào Database
  -> StreamWorker kéo luồng MJPEG từ stream_url
  -> Frontend truy xuất dữ liệu qua API
```

## 6. Sửa Cái Gì Ở Đâu?

- **All-local doi IP may host**: Sua `LOCAL_LAN_IP` trong `backend/.env` roi chay sync.
- **Đổi Domain/IP Backend public riêng**: Sửa `PUBLIC_API_URL` trong `backend/.env` rồi chạy sync.
- **Đổi mode Frontend local/hosting**: Sửa `FRONTEND_API_MODE` trong `backend/.env`.
- **Đổi Host ThingsBoard khac host backend**: Sửa `THINGSBOARD_URL`, `MQTT_TB_HOST` trong `backend/.env` rồi sync và nạp lại code cho ESP32.
- **Đổi ID hoặc Vị trí mặc định**: Sửa trong `backend/.env` (Lưu ý về ưu tiên của NVS trên thiết bị).
- **Đổi luồng Stream xem trên Web**: Chỉnh sửa trực tiếp trong Database (`cameras.stream_url`).

### 6.1 Chọn mode chuẩn nhất cho hosting

Nếu web lên production hosting và có reverse proxy `/api` về backend:

- đặt `FRONTEND_API_MODE=same_origin`
- frontend sẽ luôn gọi `/api/...`
- đây là mode gọn nhất, ít lỗi CORS nhất, không cần nhớ domain API trong code web

Nếu local dev chạy PHP ở `:8080` và backend ở `:8000`:

- đặt `FRONTEND_API_MODE=direct`
- script sync sẽ sinh `frontend/.env` với `API_URL` từ `PUBLIC_API_URL`

## 7. Quy Tắc "Vàng"

1.  **Hạ tầng**: Sửa trong `backend/.env`.
2.  **Nghiệp vụ**: Chỉnh sửa qua Database/API Backend.
3.  **Frontend**: Chỉ đọc từ Backend, không tự suy diễn dữ liệu.
4.  **Thiết bị**: Giá trị mặc định nằm trong `platformio.ini`, nhưng giá trị thực tế ưu tiên NVS.
5.  **Đồng bộ**: Luôn chạy sync config sau khi thay đổi file `.env`.
6.  **Production chuẩn nhất**: Dùng `FRONTEND_API_MODE=same_origin`.

## 8. Các Lệnh Thường Dùng

- **Đồng bộ cấu hình**: `venv\Scripts\python.exe backend\scripts\sync_local_config.py`
- **Khởi động hệ thống**: `start_system.bat`
- **Nạp code cho ESP32**: `pio run -t upload` (trong thư mục esp32-s3-devkitc-1)

---
Tài liệu liên quan: [Overview](./01_BACKEND_OVERVIEW.md) | [Database](./04_BACKEND_DATABASE.md) | [Deployment](./07_BACKEND_DEPLOYMENT.md)
