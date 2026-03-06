# 08 — Configuration & Secrets Management

## Tổng quan

Firmware dùng **2 lớp cấu hình**:
1. **`platformio.ini` [secrets]** — Build-time: URL, IP, API keys, WiFi
2. **NVS (Non-Volatile Storage)** — Runtime: token, SSID, frames_per_upload

Không có giá trị nhạy cảm nào hardcode trong source code.

---

## Lớp 1: `platformio.ini` [secrets] — Build-time config

```ini
[secrets]
; WiFi mặc định (override bởi NVS sau provisioning)
wifi_ssid     = MyNetwork
wifi_pass     = MyPassword

; ThingsBoard (self-hosted Docker)
tb_mqtt_uri   = mqtt://103.249.117.212:1883
tb_base_url   = http://103.249.117.212:8080
tb_prov_url   = http://103.249.117.212:8080/api/v1/provision

; Backend HTTP upload
backend_url   = http://103.249.117.210:3340

; MinIO / S3
minio_endpoint   = dev-s3.imespro.ai
minio_access_key = BlO00q2G...
minio_secret_key = u9J3vUk3...
minio_bucket     = cam
minio_region     = ap-southeast-1
```

Được truyền vào build compiler dưới dạng `-D` macros:
```ini
build_flags =
    -DDEFAULT_WIFI_SSID=\"${secrets.wifi_ssid}\"
    -DTHINGSBOARD_BASE_URL=\"${secrets.tb_base_url}\"
    -DMQTT_BROKER_URI=\"${secrets.tb_mqtt_uri}\"
    -DTB_PROVISION_URL=\"${secrets.tb_prov_url}\"
    -DBACKEND_UPLOAD_URL=\"${secrets.backend_url}\"
    -DMINIO_ACCESS_KEY=\"${secrets.minio_access_key}\"
    ; ...
```

Nếu thiếu bất kỳ define nào → **compile error ngay lập tức**:
```c
#ifndef MQTT_BROKER_URI
#  error "MQTT_BROKER_URI chưa định nghĩa! Thêm vào platformio.ini."
#endif
```

---

## Lớp 2: NVS — Runtime config (`app_config_t`)

```c
typedef struct {
    uint8_t  magic;              // 0xA5 = hợp lệ
    uint8_t  version;            // 2 = schema v2
    char     ssid[33];           // WiFi SSID (thay thế DEFAULT_WIFI_SSID)
    char     password[65];       // WiFi password
    char     token[97];          // ThingsBoard access token
    char     prov_key[65];       // Provisioning key
    char     prov_secret[65];    // Provisioning secret
    uint16_t frames_per_upload;  // Số frame upload MinIO tối đa
} app_config_t;
```

### Namespace NVS: `app_cfg`, Key: `config`

### Trạng thái khi load:
| State | Màu LED boot | Tác động |
|-------|-------------|---------|
| `EMPTY` | Trắng mờ | Dùng default, cần provisioning |
| `VALID` | Xanh lá sớm | Kết nối ngay |
| `MIGRATE` | Cảnh báo log | Đọc được, nhưng version cũ |

---

## NVS Operations

```c
// Đọc
app_config_load(&cfg, &state);  // Khi boot

// Lưu (tự động sau provisioning, sau ThingsBoard attr update)
app_config_save(&cfg);          // Magic + version tự động set

// Xóa (factory reset)
app_config_clear();             // Xóa toàn bộ namespace app_cfg
```

---

## Git Security

```
esp32-s3-devkitc-1/
├── platformio.ini          ← KHÔNG commit (có trong .gitignore)
├── platformio.ini.example  ← Commit được (chứa placeholder)
└── .gitignore              ← Block platformio.ini
```

**Quy trình cho developer mới:**
```bash
# 1. Clone repo
git clone ...
# 2. Copy template
cp platformio.ini.example platformio.ini
# 3. Điền key thật
nano platformio.ini
# 4. Build
idf.py build
```

---

## Thứ tự ưu tiên config

```
ThingsBoard Shared Attr (runtime)
        ▲ ưu tiên cao nhất
NVS (lưu từ provisioning / TB attr update)
        ▲
platformio.ini build_flags (mặc định)
        ▲ ưu tiên thấp nhất (bị override bởi NVS)
```

Ví dụ `frames_per_upload`:
- Build flag: không có (phải lấy từ TB attr)
- NVS: 5 (mặc định)
- TB attr update `frames_per_upload=10` → NVS cập nhật → dùng 10

---

## Thêm trường config mới

1. Thêm field vào `app_config_t` trong `app_config.h`
2. Tăng `APP_CONFIG_VERSION` (ví dụ: 2 → 3)
3. Xử lý `APP_CONFIG_STATE_MIGRATE` trong `app_config_load()` nếu cần convert dữ liệu cũ

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `platformio.ini` | Secrets + build flags |
| `platformio.ini.example` | Template an toàn cho git |
| `.gitignore` | Bảo vệ secrets |
| `include/app_config.h` | Struct + constants |
| `src/app_config.c` | NVS load/save/clear |
