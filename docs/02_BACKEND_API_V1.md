# API backend v1

Tai lieu nay mo ta contract dang chay thuc te giua ESP32, ThingsBoard va backend.

## 1. Quy uoc chung

- Prefix chung: `/api`
- Framework: FastAPI
- Web dashboard nen goi backend, khong goi truc tiep ThingsBoard
- Firmware ESP32 dung backend cho 3 viec chinh:
  - sync provisioning
  - upload frame
  - heartbeat va finalize

## 2. System endpoints

### `GET /`

Tra metadata co ban cua backend:

```json
{
  "name": "API Giam sat vi pham giao thong",
  "version": "1.0.0",
  "status": "online",
  "docs": "/docs",
  "timestamp": "2026-03-09T10:00:00"
}
```

### `GET /health`

```json
{
  "status": "healthy",
  "timestamp": "2026-03-09T10:00:00"
}
```

## 3. Camera endpoints

### `GET /api/cameras`

- Doc tu `view_camera_summary`
- Web dashboard dung endpoint nay de liet ke camera

### `GET /api/cameras/{camera_id}`

- Lay chi tiet 1 camera

### `POST /api/cameras`

- Tao camera thu cong tu backend/web

### `PUT /api/cameras/{camera_id}`

- Cap nhat metadata camera tu web
- Cac field hay dung: `camera_name`, `location`, `stream_url`, `description`, `tb_device_name`, `status`

### `DELETE /api/cameras/{camera_id}`

- Xoa camera

### `POST /api/cameras/{camera_id}/factory-reset`

- Backend goi REST API ThingsBoard
- ThingsBoard gui RPC `factoryReset` toi board

### `POST /api/cameras/provision`

Day la endpoint match chinh giua firmware va backend.

Firmware goi endpoint nay sau khi MQTT ket noi ThingsBoard va da co:

- `camera_id`
- `tb_device_id`
- `tb_device_name`
- `access_token`
- `mac_address`
- `fw_version`
- `idf_version`
- `ip_address`

Request body:

```json
{
  "camera_id": 1,
  "tb_device_id": "cam-AABBCCDDEEFF",
  "tb_device_name": "cam-AABBCCDDEEFF",
  "access_token": "token",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "fw_version": "1.0.0",
  "idf_version": "v5.3.1",
  "ip_address": "192.168.1.10"
}
```

Hanh vi backend hien tai:

- upsert vao `camera_provisioning`
- tao camera neu chua ton tai trong `cameras`
- cap nhat `status=active`
- neu `stream_url` dang trong hoac la URL noi bo tu sinh tu IP cu, backend tu cap nhat lai thanh `http://<ip_address>/stream`

## 4. Upload, heartbeat va finalize

### `POST /api/upload`

Nhan 1 frame JPEG tu firmware.

Field firmware gui:

- `file`
- `camera_id`
- `traffic_light_state`
- `operation_mode`
- `tl_state_ms`

Field API co ho tro them nhung firmware hien tai khong gui:

- `timestamp`
- `emergency`

Logic thuc te match voi firmware:

- firmware chi goi `/api/upload` khi pha hien tai la `red`
- neu den khong phai `red`, firmware khong gui full frame ma chi gui heartbeat
- backend van giu logic `skipped=true` neu mot client khac goi `/api/upload` voi `traffic_light_state != red`

Response thanh cong dien hinh:

```json
{
  "success": true,
  "camera_id": 1,
  "detections": 2,
  "quality_score": 82.4,
  "frames_buffered": 3,
  "auto_finalized": false,
  "violations": [],
  "traffic_light_state": "red",
  "operation_mode": "normal",
  "tl_state_ms": 4123,
  "finalize_reason": "need_more_frames",
  "processing_ms": 95
}
```

### `POST /api/upload/heartbeat`

Form field:

```text
camera_id=1
```

Tac dung:

- cap nhat `last_seen_at`
- danh dau `online=true` trong `camera_provisioning`

Firmware goi endpoint nay dinh ky khi board online nhung khong upload frame.

### `POST /api/finalize`

Form field:

```text
camera_id=1
```

Tac dung:

- chot buffer khung hinh da tich luy
- tao ho so vi pham neu du dieu kien

Firmware goi endpoint nay khi chuyen pha `do -> xanh`.

## 5. Dashboard endpoints

### `GET /api/dashboard/overview`

Tra so lieu tong quan:

- `total_cameras`
- `online_cameras`
- `offline_cameras`
- `violations_today`
- `violations_total`
- `generated_at`

### `GET /api/dashboard/cameras`

- Tra danh sach camera cho dashboard

### `GET /api/dashboard/recent-violations?limit=10`

- Tra danh sach vi pham gan nhat

## 6. Match chinh giua ESP32 va backend

Day la chain match dung hien tai:

`camera_id <-> mac_address <-> tb_device_name <-> access_token <-> ip_address <-> stream_url`

Trong do:

- `camera_id` la khoa nghiep vu
- `mac_address` la khoa board vat ly
- `tb_device_name` la ten ThingsBoard firmware tu sinh theo MAC
- `access_token` la khoa MQTT/OTA
- `ip_address` la dia chi LAN hien tai
- `stream_url` duoc backend chuan hoa tu `ip_address`

## 7. Ghi chu van hanh

- Backend log hien tai da tung ghi nhan cac request Supabase `401 Unauthorized` tren `view_camera_summary` va `view_violations_full`, can xac nhan lai quyen truy cap view trong moi truong chay that.
- Contract firmware/backend hien tai da khop cho provisioning, upload, heartbeat, finalize va stream URL.
