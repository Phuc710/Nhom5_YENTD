# 08 — Configuration & Secrets Management

## Tổng quan

Firmware dùng **3 lớp cấu hình**:
1. **`platformio.ini` [secrets]** — endpoint, key, WiFi mặc định
2. **`platformio.ini` [device_defaults]** — camera_id, interval, camera defaults, đèn giao thông
3. **NVS (Non-Volatile Storage)** — runtime state đã lưu như `token`, WiFi, `frames_per_upload`

Không có giá trị nhạy cảm nào hardcode trong source code.

---

## Lớp 1: `platformio.ini` [secrets] — Build-time config

```ini
[secrets]
; AP cấu hình WiFi
wifi_ap_ssid  = kaishop
wifi_ap_pass  = 1

; ThingsBoard (self-hosted Docker)
tb_mqtt_uri   = mqtt://103.249.117.212:1883
tb_base_url   = http://103.249.117.212:9090
tb_prov_url   = http://103.249.117.212:9090/api/v1/provision
provisioning_key    = YOUR_TB_PROVISIONING_KEY
provisioning_secret = YOUR_TB_PROVISIONING_SECRET

; Backend HTTP upload
backend_url   = http://103.249.117.210:8000

; MinIO / S3
minio_endpoint   = dev-s3.imespro.ai
minio_access_key = BlO00q2G...
minio_secret_key = u9J3vUk3...
minio_bucket     = cam
minio_region     = ap-southeast-1
```

## Lớp 2: `platformio.ini` [device_defaults] — Mặc định lúc boot

```ini
[device_defaults]
camera_id           = 1
save_img            = 1
capture_interval_ms = 1000
frames_per_upload   = 5
camera_xclk_hz            = 20000000
camera_frame_size_psram   = FRAMESIZE_VGA
camera_frame_size_no_psram= FRAMESIZE_QVGA
camera_jpeg_quality_psram = 10
camera_jpeg_quality_no_psram = 12
camera_fb_count_psram     = 2
camera_fb_count_no_psram  = 1
tl_pin_red        = 25
tl_pin_yellow     = 26
tl_pin_green      = 27
tl_pin_btn_red    = 32
tl_pin_btn_green  = 33
tl_red_duration_ms    = 7000
tl_yellow_duration_ms = 2000
tl_green_duration_ms  = 5000
```

Ý nghĩa:

- `secrets` là chỗ chứa thông tin nhạy cảm
- `device_defaults` là chỗ gom toàn bộ mặc định vận hành của ESP32
- `ThingsBoard shared attributes` vẫn có quyền override động khi thiết bị đang chạy

Phân biệt đúng vai trò:

- `tb_mqtt_uri`, `tb_base_url`, `tb_prov_url`:
  endpoint của ThingsBoard
- `minio_access_key`, `minio_secret_key`:
  key của MinIO/S3 để lưu ảnh
- `provisioning_key`, `provisioning_secret`:
  provisioning credentials thật của ThingsBoard, hiện nên khai báo tập trung trong `platformio.ini`
  và sẽ được nạp vào `app_config_t` khi NVS đang trống

Được truyền vào build compiler dưới dạng `-D` macros:
```ini
build_flags =
    -DWIFI_MANAGER_AP_SSID=\"${secrets.wifi_ap_ssid}\"
    -DWIFI_MANAGER_AP_PASS=\"${secrets.wifi_ap_pass}\"
    -DTHINGSBOARD_BASE_URL=\"${secrets.tb_base_url}\"
    -DMQTT_BROKER_URI=\"${secrets.tb_mqtt_uri}\"
    -DTB_PROVISION_URL=\"${secrets.tb_prov_url}\"
    -DDEFAULT_TB_PROVISIONING_KEY=\"${secrets.provisioning_key}\"
    -DDEFAULT_TB_PROVISIONING_SECRET=\"${secrets.provisioning_secret}\"
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

## Lớp 3: NVS — Runtime config (`app_config_t`)

```c
typedef struct {
    uint8_t  magic;              // 0xA5 = hợp lệ
    uint8_t  version;            // 2 = schema v2
    char     ssid[33];           // WiFi SSID lưu trong NVS sau khi cấu hình qua AP portal
    char     password[65];       // WiFi password
    char     token[97];          // ThingsBoard access token
    char     provisioning_key[65];    // ThingsBoard provisioning key
    char     provisioning_secret[65]; // ThingsBoard provisioning secret
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

// Xóa toàn bộ (factory reset)
app_config_clear();             // Xóa toàn bộ namespace app_cfg

// Chỉ xóa token cũ để provision lại
app_config_clear_token();       // Giữ WiFi + provisioning credentials
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
platformio.ini [device_defaults] + build_flags
        ▲ ưu tiên thấp nhất (bị override bởi NVS)
```

Ví dụ `frames_per_upload`:
- `platformio.ini [device_defaults]`: `5`
- NVS: lưu lại giá trị gần nhất nếu firmware đã ghi
- TB attr update `frames_per_upload=10` → NVS cập nhật → dùng `10`

## Reboot, provision lại, factory reset

Ba thao tác này khác nhau:

- `reboot`: chỉ khởi động lại, **không xóa NVS**
- `reprovision`: **chỉ xóa access token cũ**, giữ WiFi và `provisioning_key/provisioning_secret`
- `factory reset`: xóa toàn bộ NVS

Nghĩa là nếu bạn đổi `platformio.ini` mà board đang có token cũ trong NVS:

- chỉ `reboot` thì token cũ vẫn còn
- `reprovision` thì token cũ bị xóa, boot lên sẽ xin token mới
- `factory reset` thì xóa sạch toàn bộ cấu hình đã lưu

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
| `src/app_config.c` | NVS load/save/clear/clear_token |

## Cap nhat WiFi Manager

Phan WiFi mac dinh trong tai lieu cu da khong con dung voi code hien tai.

Hien tai:

- `platformio.ini` chi giu AP config cho WiFi Manager:
  - `wifi_ap_ssid = kaishop`
  - `wifi_ap_pass = 1`
- WiFi thuc te de board len mang se duoc nhap qua portal AP va luu vao NVS.
- Source code khong con hardcode `DEFAULT_WIFI_SSID` / `DEFAULT_WIFI_PASS`.
- NVS van la noi luu `ssid`, `password`, `token`, `provisioning_key`, `provisioning_secret`.

Luu y quan trong:

- SoftAP ESP-IDF chi bat WPA/WPA2 khi password dai tu 8 ky tu tro len.
- Neu `wifi_ap_pass` ngan hon 8 ky tu, firmware se phat `open AP` de tranh fail boot.

Build flags WiFi moi:

```ini
build_flags =
    '-DWIFI_MANAGER_AP_SSID="${secrets.wifi_ap_ssid}"'
    '-DWIFI_MANAGER_AP_PASS="${secrets.wifi_ap_pass}"'
```
