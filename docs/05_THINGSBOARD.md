# Hướng Dẫn Cấu Hình ThingsBoard

## Tổng Quan

ThingsBoard quản lý tất cả ESP32 devices (camera + đèn giao thông) qua MQTT.

**URL**: `https://tcm-iot.imespro.ai`
**MQTT Broker**: `103.249.117.212:1883`

## Bước 1: Tạo Device Profile - ESP32-CAM

### 1.1. Tạo Profile

1. Login ThingsBoard
2. **Profiles → Device Profiles**
3. Click **"+ Add Device Profile"**

**Thông tin**:
```
Name: camera_AI
Device Type: ESP32-CAM
Transport Type: Default
Rule Chain: Root Rule Chain
```

### 1.2. Bật Auto-Provisioning

Trong Device Profile `camera_AI`:

1. Tab **"Device provisioning"**
2. Chọn: **"Allow device provisioning"**
3. Điền:
   ```
   Provision Device Key: 3scphnz74pkmk1snfj
   Provision Device Secret: u7sw1jjakceaaign3o
   ```

⚠️ **Lưu ý**: Đổi keys này trong production!

### 1.3. Cấu Hình Telemetry Keys

Tab **"Telemetry"**, thêm các keys:

| Key | Type | Mô tả |
|-----|------|-------|
| `status` | String | Trạng thái online/offline |
| `upload` | String | Kết quả upload (success/failed) |
| `free_heap` | Number | RAM còn trống (bytes) |
| `uptime_sec` | Number | Thời gian hoạt động (giây) |

### 1.4. Cấu Hình Shared Attributes

Tab **"Attributes"**, định nghĩa shared attributes:

| Attribute | Type | Default | Mô tả |
|-----------|------|---------|-------|
| `camera_id` | Number | 1 | ID camera (1, 2, 3) |
| `capture_interval` | Number | 1000 | Khoảng cách chụp (ms) |
| `traffic_light_state` | String | "red" | Trạng thái đèn |
| `fw_version` | String | "1.0.0" | Version firmware |
| `fw_url` | String | "" | URL firmware OTA |

## Bước 2: Tạo Device Profile - Traffic Light

### 2.1. Tạo Profile

**Profiles → Device Profiles → Add**

```
Name: traffic_light
Device Type: ESP32-TrafficLight
Transport Type: Default
```

### 2.2. Telemetry Keys

| Key | Type | Mô tả |
|-----|------|-------|
| `traffic_light_state` | String | red/yellow/green |
| `operation_mode` | String | normal/emergency_red/emergency_green |
| `uptime_sec` | Number | Uptime (giây) |

### 2.3. RPC Commands

Tab **"RPC"**, thêm methods:

```json
{
  "methods": [
    "setNormalMode",
    "setEmergencyRed",
    "setEmergencyGreen"
  ]
}
```

## Bước 3: Tạo Devices

### 3.1. Auto-Provisioning (Khuyến nghị)

ESP32 tự động tạo device khi khởi động lần đầu:

1. Flash firmware ESP32
2. ESP32 gọi `/api/v1/provision`
3. ThingsBoard tự tạo device
4. Trả token về ESP32
5. ESP32 lưu token vào NVS

**Device name format**: `ESP32CAM_AABBCC` (từ MAC address)

### 3.2. Manual Create (Tùy chọn)

**Devices → Add Device**

```
Name: ESP32CAM_001
Device Profile: camera_AI
```

Copy **Access Token** và paste vào ESP32 code.

## Bước 4: Set Shared Attributes

### 4.1. Cho ESP32-CAM

1. **Devices → Chọn ESP32-CAM → Attributes**
2. Click **"+"** ở phần **Shared attributes**
3. Thêm:

```json
{
  "camera_id": 1,
  "capture_interval": 1000,
  "traffic_light_state": "red"
}
```

### 4.2. Cho Traffic Light

```json
{
  "traffic_light_id": 1,
  "red_duration": 7000,
  "yellow_duration": 2000,
  "green_duration": 5000
}
```

## Bước 5: Rule Chains

### 5.1. Tạo Rule Chain Mới

**Rule Chains → Add Rule Chain**

```
Name: Camera Telemetry Processing
```

### 5.2. Thêm Nodes

#### Node 1: Save Timeseries
```
Type: save timeseries
Name: Save Telemetry to DB
```

Kết nối: **Input → Save Timeseries**

#### Node 2: Script - Check Free Heap
```
Type: script
Name: Check Low Memory

Script:
if (msg.free_heap < 50000) {
    return {msg: msg, metadata: metadata, msgType: "alarm"};
}
return {msg: msg, metadata: metadata, msgType: "ok"};
```

Kết nối: **Save Timeseries → Check Free Heap**

#### Node 3: Create Alarm
```
Type: create alarm
Name: Low Memory Alarm
Alarm Type: Low Memory
Severity: WARNING
```

Kết nối: **Check Free Heap (alarm) → Create Alarm**

### 5.3. Assign Rule Chain

1. **Device Profiles → camera_AI**
2. Tab **"Rule Chain"**
3. Chọn: `Camera Telemetry Processing`

## Bước 6: Dashboard

### 6.1. Tạo Dashboard

**Dashboards → Add Dashboard**

```
Name: Traffic Cameras Monitor
```

### 6.2. Thêm Widgets

#### Widget 1: Entity Cards (Camera Status)

**Type**: Entity Cards

**Datasources**:
```json
{
  "type": "device",
  "deviceTypes": ["ESP32-CAM"]
}
```

**Display**:
- Status
- Free Heap
- Upload Count
- Last Update

#### Widget 2: Time Series Chart

**Type**: Time Series Chart

**Keys**: 
- `free_heap`
- `uptime_sec`

**Time range**: Last 24 hours

#### Widget 3: Map

**Type**: Map

**Datasources**: All cameras

**Markers**: Show camera locations

#### Widget 4: Alarms Table

**Type**: Alarms Table

**Filter**: Camera devices only

## Bước 7: OTA Update

### 7.1. Upload Firmware

1. **Dashboards → Settings → OTA Updates**
2. Click **"Upload firmware"**
3. Chọn file `.bin`
4. Nhập:
   - Title: `ESP32-CAM Firmware`
   - Version: `1.0.1`
   - Checksum: (optional)

### 7.2. Trigger OTA

**Cách 1**: Set Shared Attributes

1. **Devices → ESP32-CAM → Attributes**
2. Thêm/sửa shared attributes:

```json
{
  "fw_version": "1.0.1",
  "fw_url": "https://your-server.com/firmware.bin"
}
```

ESP32 tự động:
- Nhận attributes
- So sánh version
- Download & flash

**Cách 2**: RPC Command (nâng cao)

```json
{
  "method": "ota_update",
  "params": {
    "url": "https://..."
  }
}
```

## Bước 8: Alarms & Notifications

### 8.1. Tạo Alarm Rule

**Rule Chains → Root Rule Chain → Edit**

Thêm node:

```
Type: originator attributes
Name: Check Device Offline

Script:
var lastActivityTime = metadata.lastActivityTime;
var now = Date.now();
if (now - lastActivityTime > 300000) { // 5 minutes
    return {msg: msg, metadata: metadata, msgType: "alarm"};
}
```

### 8.2. Send Email Notification

Thêm node:

```
Type: send email
Name: Send Offline Alert

To: admin@example.com
Subject: Device Offline
Body: Device {{deviceName}} is offline
```

## Provisioning Flow Chi Tiết

```
1. ESP32 boot lần đầu
   ↓
2. Kết nối WiFi
   ↓
3. HTTP POST /api/v1/provision
   Request:
   {
     "deviceName": "ESP32CAM_AABBCC",
     "provisionDeviceKey": "3scphnz74pkmk1snfj",
     "provisionDeviceSecret": "u7sw1jjakceaaign3o"
   }
   ↓
4. ThingsBoard kiểm tra keys
   ↓
5. Tạo device mới (nếu chưa có)
   ↓
6. Response:
   {
     "status": "SUCCESS",
     "credentialsType": "ACCESS_TOKEN",
     "credentialsValue": "eyJhbGc..."
   }
   ↓
7. ESP32 lưu token vào NVS
   ↓
8. Kết nối MQTT với token
   ↓
9. Subscribe topics:
   - v1/devices/me/rpc/request/+
   - v1/devices/me/attributes
   ↓
10. Request shared attributes
   ↓
11. ThingsBoard gửi attributes về
   ↓
12. ESP32 bắt đầu hoạt động
```

## MQTT Topics

### ESP32 → ThingsBoard

| Topic | Mục đích | Payload |
|-------|----------|---------|
| `v1/devices/me/telemetry` | Gửi telemetry | `{"status":"online"}` |
| `v1/devices/me/attributes` | Gửi client attributes | `{"ip":"192.168.1.100"}` |
| `v1/devices/me/attributes/request/1` | Request shared attributes | `{"sharedKeys":"camera_id"}` |

### ThingsBoard → ESP32

| Topic | Mục đích | Payload |
|-------|----------|---------|
| `v1/devices/me/attributes` | Shared attributes update | `{"camera_id":1}` |
| `v1/devices/me/attributes/response/+` | Response attributes | `{"shared":{...}}` |
| `v1/devices/me/rpc/request/+` | RPC commands | `{"method":"reboot"}` |

## Ví Dụ Thực Tế

### Set Camera ID

**ThingsBoard Dashboard**:
1. Devices → ESP32CAM_001 → Attributes
2. Add shared attribute:
   ```json
   {"camera_id": 1}
   ```

**ESP32 nhận**:
```
[MQTT] Message: v1/devices/me/attributes
[MQTT] Camera ID: 1
```

### Trigger OTA Update

**ThingsBoard**:
```json
{
  "fw_version": "1.0.1",
  "fw_url": "https://example.com/firmware.bin"
}
```

**ESP32**:
```
[MQTT] 🔄 Nhận OTA attributes từ ThingsBoard
[MQTT] FW Version: 1.0.1
[MQTT] FW URL: https://...
[OTA] Phát hiện firmware mới: 1.0.1
[OTA] 🔄 BẮT ĐẦU OTA UPDATE
...
[OTA] ✅ UPDATE THÀNH CÔNG!
```

## Xử Lý Sự Cố

### Device không provision được

**Lỗi**: `Provision failed: 404`

**Giải pháp**:
1. Kiểm tra Device Profile có bật provisioning
2. Verify provision keys đúng
3. Xem ThingsBoard logs: `/var/log/thingsboard/thingsboard.log`

### MQTT connection refused

**Lỗi**: `MQTT failed, rc=5`

**Giải pháp**:
1. Token không hợp lệ → Provision lại
2. Device bị xóa → ESP32 tự provision lại
3. MQTT broker down → Kiểm tra ThingsBoard service

### Attributes không update

**Nguyên nhân**:
- ESP32 chưa subscribe `v1/devices/me/attributes`
- Attributes là "client" thay vì "shared"
- MQTT QoS = 0 (mất message)

**Giải pháp**:
```cpp
mqttClient.subscribe("v1/devices/me/attributes", 1); // QoS = 1
```

## Best Practices

### 1. Security

- ✅ Đổi provision keys trong production
- ✅ Dùng MQTTS (port 8883) thay vì MQTT (1883)
- ✅ Rotate tokens định kỳ
- ✅ Enable 2FA cho ThingsBoard login

### 2. Performance

- ✅ Giảm telemetry frequency (mỗi 10s thay vì 1s)
- ✅ Batch telemetry (gửi nhiều keys cùng lúc)
- ✅ Dùng QoS = 0 cho telemetry không quan trọng

### 3. Monitoring

- ✅ Set alarms cho device offline
- ✅ Monitor free heap < 50KB
- ✅ Track upload success rate
- ✅ Dashboard cho từng camera location

## Tài Liệu Tham Khảo

- [ThingsBoard Docs](https://thingsboard.io/docs/)
- [MQTT Protocol](https://mqtt.org/)
- [Device Provisioning](https://thingsboard.io/docs/user-guide/device-provisioning/)
