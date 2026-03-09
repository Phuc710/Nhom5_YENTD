# MQTT, Attributes, Telemetry va RPC

## 1. Topic MQTT dang dung

Theo firmware hien tai:

- `v1/devices/me/telemetry`
- `v1/devices/me/attributes`
- `v1/devices/me/attributes/request/1`
- `v1/devices/me/rpc/request/+`
- `v1/devices/me/rpc/response/<id>`

## 2. Telemetry

Telemetry la du lieu runtime thay doi lien tuc. Firmware dang gui:

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
- `status`
- `ip_address`
- `stream_url`
- `backend_sync`

## 3. Shared attributes

ThingsBoard day xuong firmware:

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

## 4. Client attributes

Firmware dang gui len ThingsBoard:

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

OTA state gui them:

```json
{ "fw_state": "DOWNLOADING" }
{ "fw_state": "UPDATED" }
{ "fw_state": "FAILED", "fw_error": "..." }
```

## 5. MQTT connect flow

1. firmware co token
2. MQTT connect
3. subscribe RPC va attributes
4. request shared attributes
5. publish runtime snapshot gom client attributes + telemetry
6. backend sync provisioning duoc danh dau va retry den khi thanh cong

## 6. RPC methods

### Camera

- `setResolution`
- `setQuality`
- `setInterval`

### He thong

- `reboot`
- `reprovision`
- `factoryReset`
- `getStatus`
- `startOTA`

### Den giao thong

- `setNormalMode`
- `setEmergencyRed`
- `setEmergencyGreen`
- `getTrafficStatus`

## 7. Match voi backend

- ThingsBoard la lop dieu phoi
- backend la lop chuan hoa cho dashboard
- firmware sync danh tinh va IP ve backend
- web dashboard chi nen doc backend
