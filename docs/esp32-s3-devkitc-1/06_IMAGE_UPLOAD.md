# 06 — Image Upload (HTTP Backend + MinIO/S3)

## Tổng quan

`uploader_task` nhận frame từ `g_frame_queue` và chạy theo logic mới:
1. **Pha đỏ / emergency_red**: upload frame lên backend để detect + buffer, đồng thời có thể lưu MinIO
2. **Pha xanh / vàng**: không upload full frame, chỉ heartbeat để giữ camera online
3. **Chuyển đỏ -> xanh**: gọi `POST /api/finalize` để backend chốt vi phạm

---

## Flow `uploader_task`

```
uploader_task() khởi động
        │
        ▼
Vòng lặp:
  ├─ Check epoch đổi (frames_per_upload thay đổi) → reset bộ đếm MinIO
  │
  ├─ xQueueReceive(g_frame_queue, &msg, 100ms)
  │   Không có frame → tiếp tục chờ
  │
  ├─ Đọc trạng thái đèn hiện tại từ traffic_light
  │
  ├─ Nếu vừa chuyển đỏ -> xanh:
  │     POST /api/finalize
  │
  ├─ Nếu không phải pha đỏ:
  │     heartbeat định kỳ /api/upload/heartbeat
  │     bỏ qua upload ảnh
  │
  ├─ [A] Upload Backend HTTP khi đang đỏ (với retry):
  │       for r in range(HTTP_MAX_RETRY_COUNT=3):
  │         send_http(&msg) → OK: break / FAIL: delay 1s
  │       OK  → g_send_success++ / LED giữ nguyên
  │       FAIL → g_send_fail++ / LED nháy đỏ / report event
  │
  ├─ [B] Upload MinIO (nếu cấu hình & chưa đạt limit):
  │       s_minio_sent < g_frames_per_upload?
  │         YES → send_minio(&msg)
  │         NO  → bỏ qua, log 1 lần
  │
  ├─ [C] Check lệnh đổi interval từ g_mqtt_cmd_queue
  │
  └─ heap_caps_free(msg.data) ← Giải phóng PSRAM
```

---

## Upload Backend HTTP (`send_http`)

### Request:
```
POST http://<BACKEND_URL>/api/upload
Content-Type: multipart/form-data; boundary=----EspCamBndry
Authorization: Bearer <token>

------EspCamBndry
Content-Disposition: form-data; name="camera_id"

1
------EspCamBndry
Content-Disposition: form-data; name="traffic_light_state"

red
------EspCamBndry
Content-Disposition: form-data; name="operation_mode"

normal
------EspCamBndry
Content-Disposition: form-data; name="tl_state_ms"

4123
------EspCamBndry
Content-Disposition: form-data; name="file"; filename="img.jpg"
Content-Type: image/jpeg

<JPEG binary data>
------EspCamBndry--
```

### Heartbeat khi không ở pha đỏ

```http
POST http://<BACKEND_URL>/api/upload/heartbeat
Content-Type: application/x-www-form-urlencoded

camera_id=1
```

### Finalize khi chuyển đỏ -> xanh

```http
POST http://<BACKEND_URL>/api/finalize
Content-Type: application/x-www-form-urlencoded

camera_id=1
```

### Telemetry export (đọc bởi `health_task`):
```c
g_last_upload_ok  = (http_code >= 200 && http_code < 300)
g_last_http_code  = code      // HTTP status code cuối
g_last_latency_ms = (t1-t0)/1000  // Độ trễ (ms)
```
→ Gửi lên ThingsBoard telemetry: `upload_ok`, `last_http_code`, `latency_ms`

---

## Upload MinIO/S3 (`send_minio`)

Dùng **AWS Signature Version 4 (SigV4)** — upload trực tiếp không qua server trung gian.

### Quy trình ký request:
```
1. Tạo date/amz_date từ SNTP time
   Yêu cầu: đồng hồ đồng bộ (nếu không → bỏ qua, log cảnh báo)

2. Xây canonical request:
   PUT /<bucket>/<camera_id>/<index>.jpg
   host: minio_endpoint
   x-amz-content-sha256: sha256(jpeg_data)
   x-amz-date: 20260306T140000Z

3. Tính signing key:
   kDate   = HMAC-SHA256("AWS4" + secret_key, date)
   kRegion = HMAC-SHA256(kDate, region)
   kService= HMAC-SHA256(kRegion, "s3")
   kSigning= HMAC-SHA256(kService, "aws4_request")

4. Tính signature:
   signature = HMAC-SHA256(kSigning, StringToSign)

5. Gửi:
   PUT http(s)://minio_endpoint/<bucket>/<camera_id>/<index>.jpg
   Authorization: AWS4-HMAC-SHA256 Credential=..., Signature=...
```

### Đặt tên file trong MinIO:
```
<camera_id>/<index>.jpg
Ví dụ: 1/1.jpg, 1/2.jpg, ..., 1/5.jpg (nếu frames_per_upload=5)
```

---

## Giới hạn MinIO (`frames_per_upload`)

```
g_frames_per_upload = 5 (mặc định, thay đổi qua ThingsBoard shared attr)

Epoch đếm:  mỗi lần frames_per_upload thay đổi → reset bộ đếm
s_minio_sent:  0 → tăng dần mỗi upload thành công
s_minio_sent >= g_frames_per_upload → DỪNG upload MinIO cho epoch này
```

Ví dụ: `frames_per_upload=5` → chỉ upload 5 ảnh đầu của phiên làm việc.

---

## LED feedback

| Trạng thái | LED |
|-----------|-----|
| Upload thành công sau lỗi | Trắng `(32,32,32)` |
| Upload thất bại liên tục | Nháy đỏ `(48,0,0)` ↔ tắt |
| Hệ thống bình thường | LED giữ nguyên (white) |

---

## Cấu hình trong `platformio.ini`

```ini
[secrets]
backend_url      = http://103.249.117.210:8000
minio_endpoint   = dev-s3.imespro.ai
minio_access_key = BlO00q2G...
minio_secret_key = u9J3vUk3...
minio_bucket     = cam
minio_region     = ap-southeast-1
```

MinIO/S3 TLS: thêm `-DMINIO_USE_TLS=1` vào build_flags.

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/uploader_task.c` | Upload logic (HTTP + MinIO SigV4) |
| `include/uploader_task.h` | API setters |
| `include/task_common.h` | `frame_msg_t`, retry constants |
| `src/health_task.c` | Đọc `g_last_upload_ok` / `latency_ms` |
