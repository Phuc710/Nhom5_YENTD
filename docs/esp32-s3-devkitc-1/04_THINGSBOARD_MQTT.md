# 04 — ThingsBoard MQTT Connection

## Tổng quan

Firmware kết nối ThingsBoard qua giao thức **MQTT** với access token làm username.  
`mqtt_task` chạy suốt vòng đời thiết bị — xử lý publish telemetry, subscribe RPC, và auto-reconnect.

---

## Kết nối MQTT

```
Broker URI: mqtt://<TB_HOST>:1883
Username:   <access_token>        (lấy từ NVS sau provisioning)
Password:   (trống)
Keepalive:  30s
```

### Các topic sử dụng:

| Topic | Hướng | Mô tả |
|-------|-------|-------|
| `v1/devices/me/telemetry` | Thiết bị → TB | Gửi dữ liệu đo lường |
| `v1/devices/me/attributes` | 2 chiều | Publish client attrs / nhận shared attrs |
| `v1/devices/me/attributes/request/1` | Thiết bị → TB | Yêu cầu lấy shared attrs |
| `v1/devices/me/rpc/request/+` | TB → Thiết bị | Nhận lệnh RPC |
| `v1/devices/me/rpc/response/<id>` | Thiết bị → TB | Trả lời RPC |

---

## Flow MQTT kết nối

```
mqtt_task() khởi động
        │
        ▼
mqtt_client_create(token):
  esp_mqtt_client_init({
    uri: MQTT_BROKER_URI,
    username: token,
    keepalive: 30
  })
  esp_mqtt_client_register_event(mqtt_evt_handler)
  esp_mqtt_client_start()
        │
        ▼
MQTT_EVENT_CONNECTED:
  ├─ Subscribe v1/devices/me/rpc/request/+
  ├─ Subscribe v1/devices/me/attributes
  ├─ Publish attributes/request/1 → yêu cầu shared attrs
  │    {"sharedKeys": "save_img,camera_id,frames_per_upload,..."}
  ├─ Publish telemetry: {"status": "online"}
  └─ Publish client attributes:
       {"Model": "...", "fw_version": "...", "mac": "...", "camera_id": 1}
```

---

## Shared Attributes (TB → Thiết bị)

Nhận khi: (1) yêu cầu lúc connect, (2) TB cập nhật giá trị

| Key | Kiểu | Tác động |
|-----|------|---------|
| `save_img` | bool | Bật/tắt lưu ảnh vào backend |
| `camera_id` / `cam_id` | int | ID camera gửi kèm khi upload |
| `frames_per_upload` | int | Số frame tối đa upload MinIO/session |
| `jpeg_quality` | int | Đổi JPEG quality camera (0–63) |
| `resolution` | int | Đổi framesize camera (enum FRAMESIZE_*) |
| `reboot` | bool | Khởi động lại thiết bị |
| `factory_reset` / `reset` | bool | Xóa NVS + reboot |
| `fw_title` + `fw_version` | string | Kích hoạt OTA update |
| `ota_url` / `fw_url` | string | OTA từ URL trực tiếp |
| `active` | bool | (Dự phòng) bật/tắt chụp ảnh |

---

## Client Attributes (Thiết bị → TB)

Gửi lúc kết nối MQTT và sau OTA thành công:

```json
{
  "Model":      "GOOUUU Tech ESP32-S3-CAM N16R8",
  "fw_version": "1.0.0",
  "camera_id":  1,
  "mac":        "AA:BB:CC:DD:EE:FF",
  "idf_ver":    "v5.3.1"
}
```

Gửi OTA state:
```json
{ "fw_state": "DOWNLOADING" | "UPDATED" | "FAILED" }
```

---

## RPC Methods (TB → Thiết bị)

Gọi từ: TB UI → Device → RPC tab hoặc API

| Method | Params | Mô tả |
|--------|--------|-------|
| `setResolution` | `{"framesize": 6}` | Đổi độ phân giải (FRAMESIZE_VGA=6) |
| `setQuality` | `{"quality": 10}` | Đổi JPEG quality |
| `setInterval` | `{"interval_ms": 500}` | Đổi tần suất chụp |
| `reboot` | — | Reboot thiết bị |
| `startOTA` | `{"url": "http://..."}` | Kích hoạt OTA từ URL |
| `getStatus` | — | Trả về trạng thái hiện tại |
| `factoryReset` | — | Xóa NVS + reboot |

### Ví dụ gọi RPC qua ThingsBoard REST API:
```bash
curl -X POST http://<TB_HOST>:8080/api/v1/<TOKEN>/rpc \
  -H "Content-Type: application/json" \
  -d '{"method": "setResolution", "params": {"framesize": 5}}'
```

---

## Auto Reconnect & Re-provision

```
MQTT_EVENT_DISCONNECTED
        │
        ▼
s_connected = false, s_disconnect_tick = now
        │
        ▼ (loop trong mqtt_task, mỗi 3s)
has_prov_credentials?
    YES → tb_provision_device() → lấy token mới → mqtt_client_create()
    NO  → chờ WiFi recover → MQTT tự reconnect (esp_mqtt build-in backoff)
```

---

## Publish Telemetry

Telemetry được `health_task` thu thập và đẩy vào `g_telemetry_queue`.  
`mqtt_task` đọc queue và publish mỗi vòng lặp 50ms:

```c
while (xQueueReceive(g_telemetry_queue, &telem, 100ms)):
    mqtt_app_publish_telemetry(&telem)
    → esp_mqtt_client_publish(TB_TOPIC_TELEMETRY, json_buf, QoS=1)
```

---

## Cấu hình tường lửa cần mở

| Port | Protocol | Mô tả |
|------|----------|-------|
| 1883 | TCP/MQTT | Kết nối MQTT không mã hóa |
| 8080 | TCP/HTTP | Provisioning + OTA package download |
| 8883 | TCP/MQTTS | MQTT có TLS (nếu dùng) |

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/mqtt_app.c` | Toàn bộ MQTT logic |
| `include/mqtt_app.h` | Topics, URLs, API |
| `platformio.ini` | `MQTT_BROKER_URI`, `THINGSBOARD_BASE_URL` |
