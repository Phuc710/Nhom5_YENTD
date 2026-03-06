# 07 — Health Monitoring & Telemetry

## Tổng quan

`health_task` chạy mỗi 5 giây để thu thập số liệu sức khỏe thiết bị, log ra Serial, và gửi telemetry đầy đủ lên ThingsBoard mỗi 30 giây.

---

## Flow `health_task`

```
health_task() khởi động
        │
        ▼
Vòng lặp (mỗi HEALTH_CHECK_INTERVAL_MS = 5000ms):
  │
  ├─ Thu thập số liệu:
  │   free_heap      = esp_get_free_heap_size()
  │   min_free_heap  = esp_get_minimum_free_heap_size()
  │   wifi_rssi      = get_wifi_rssi()   ← esp_wifi_sta_get_ap_info()
  │   uptime         = esp_timer_get_time() / 1e6
  │   frame_count    = g_frame_count     (camera_task cập nhật)
  │   send_success   = g_send_success    (uploader_task cập nhật)
  │   send_fail      = g_send_fail       (uploader_task cập nhật)
  │   camera_ok      = g_camera_ok
  │   upload_ok      = g_last_upload_ok  (uploader_task export)
  │   last_http_code = g_last_http_code
  │   latency_ms     = g_last_latency_ms
  │
  ├─ Log ra Serial:
  │   "Heap: 120000 B | MinHeap: 80000 B | RSSI: -65 dBm | Uptime: 120s
  │    Frame: 500 | OK: 498 | Fail: 2 | Cam: OK"
  │
  └─ Mỗi TELEMETRY_INTERVAL_MS = 30000ms:
       Đẩy vào g_telemetry_queue → mqtt_task publish
```

---

## Telemetry JSON gửi lên ThingsBoard

```json
{
  "free_heap":      125440,
  "min_free_heap":  98304,
  "Wifi_Status":    -65,
  "frame_count":    1200,
  "send_success":   1198,
  "send_fail":      2,
  "uptime_sec":     3600,
  "camera_ok":      true,
  "mqtt_connected": true,
  "net_error":      false,
  "upload_ok":      true,
  "last_http_code": 200,
  "latency_ms":     187
}
```

> **Lưu ý tên field**: `Wifi_Status` (viết hoa W, S) — khớp với ThingsBoard dashboard widget mặc định.

---

## Dashboard ThingsBoard gợi ý

| Widget | Key | Mô tả |
|--------|-----|-------|
| Gauge | `Wifi_Status` | Cường độ sóng (-100 đến 0 dBm) |
| Value Card | `latency_ms` | Độ trễ upload (ms) |
| Value Card | `free_heap` | Heap tự do |
| Timeseries | `send_success`, `send_fail` | Thống kê upload |
| Timeseries | `uptime_sec` | Uptime |
| Bool indicator | `camera_ok`, `upload_ok` | Trạng thái OK/Lỗi |
| Alarm | `net_error == true` | Cảnh báo mất mạng |

---

## Telemetry Event (tức thời)

Ngoài telemetry định kỳ, các event tức thời cũng được gửi qua `task_manager_report_event()`:

```json
{ "event": "upload_fail", "details": "HTTP thất bại" }
{ "event": "ota_start",   "details": "http://...fw.bin" }
```

Gọi từ bất kỳ task nào:
```c
task_manager_report_event("lỗi_tên", "chi tiết lỗi");
```

---

## Status Telemetry (MQTT connect/disconnect)

```json
{ "status": "online" }   // Publish ngay sau khi MQTT connect
```

---

## Cấu hình interval

| Constant | Mặc định | File |
|----------|----------|------|
| `HEALTH_CHECK_INTERVAL_MS` | 5000 ms | `task_common.h` |
| `TELEMETRY_INTERVAL_MS` | 30000 ms | `task_common.h` |
| `TELEMETRY_QUEUE_DEPTH` | 8 | `task_common.h` |

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/health_task.c` | Thu thập + gửi queue |
| `src/uploader_task.c` | Export `g_last_upload_ok`, `latency_ms` |
| `src/task_manager.c` | Export `g_frame_count`, `g_send_*` |
| `src/mqtt_app.c` | Consume queue → publish TB |
| `include/task_common.h` | `health_telemetry_t`, constants |
