# 04 - ThingsBoard MQTT

## Tong quan

Firmware ket noi ThingsBoard qua MQTT voi `access_token` lam username.

`mqtt_task` dam nhan:

- publish telemetry
- publish client attributes
- nhan shared attributes
- nhan RPC
- retry provisioning neu can
- sync provisioning ve backend

## Topic dang dung

- `v1/devices/me/telemetry`
- `v1/devices/me/attributes`
- `v1/devices/me/attributes/request/1`
- `v1/devices/me/rpc/request/+`
- `v1/devices/me/rpc/response/<id>`

## Shared attributes firmware dang xu ly

- `save_img`
- `camera_id`
- `cam_id`
- `frames_per_upload`
- `capture_interval_ms`
- `interval_ms`
- `jpeg_quality`
- `resolution`
- `reboot`
- `reprovision`
- `clear_token`
- `factory_reset`
- `reset`
- `fw_title`
- `fw_version`
- `ota_url`
- `fw_url`
- `tl_red_ms`
- `tl_yellow_ms`
- `tl_green_ms`
- `tl_mode`

## Client attributes va runtime snapshot firmware dang gui

Khi MQTT connect, firmware gui runtime snapshot gom client attributes va telemetry runtime:

```json
{
  "Model": "GOOUUU Tech ESP32-S3-CAM N16R8",
  "fw_version": "1.0.0",
  "camera_id": 1,
  "mac": "AA:BB:CC:DD:EE:FF",
  "idf_ver": "v5.3.1",
  "ip_address": "192.168.1.10",
  "stream_url": "http://192.168.1.10/stream",
  "backend_url": "http://backend:8000",
  "device_status": "online",
  "backend_sync": "pending"
}
```

Telemetry runtime dang gui them:

- `upload_ok`
- `last_http_code`
- `latency_ms`
- `Wifi_Status`
- `free_heap`
- `min_free_heap`
- `frame_count`
- `send_success`
- `send_fail`
- `uptime_sec`
- `camera_ok`
- `mqtt_connected`
- `net_error`
- `traffic_light_state`
- `operation_mode`
- `tl_state_ms`

## Flow MQTT connect dung hien tai

`MQTT_EVENT_CONNECTED`:

1. subscribe RPC
2. subscribe attributes
3. request shared attributes
4. publish runtime snapshot `status=online`, `backend_sync=pending`
5. danh dau can sync provisioning ve backend

## RPC methods dang ho tro

### Nhom camera

- `setResolution`
- `setQuality`
- `setInterval`

### Nhom he thong

- `reboot`
- `reprovision`
- `factoryReset`
- `getStatus`
- `startOTA`

### Nhom den giao thong

- `setNormalMode`
- `setEmergencyRed`
- `setEmergencyGreen`
- `getTrafficStatus`

## Ghi chu match voi backend

- Sau khi MQTT connect, firmware tu sync `camera_id + mac + tb_device_name + token + ip + fw` ve backend
- Khi `camera_id` doi tu shared attributes, firmware danh dau sync lai
- `stream_url` duoc firmware va backend thong nhat theo cong thuc `http://<ip_address>/stream`
