# 02 — ThingsBoard Provisioning

## Tổng quan

**Provisioning** là quá trình đăng ký thiết bị mới lên ThingsBoard và nhận về **access token** để xác thực MQTT.  
Token được lưu vào NVS → các lần boot sau dùng lại, không cần provisioning lại.

---

## Khi nào chạy provisioning?

```
Boot → app_config_load() → token trống?
                                │
                     YES ──────►│ tb_has_prov_credentials(cfg)?
                                │         │
                                │   YES ──►  tb_provision_device()
                                │   NO  ──►  Bỏ qua (MQTT task sẽ thử sau)
                                │
                      NO ──────►  Bỏ qua provisioning (đã có token)
```

**Provisioning credentials** (prov_key, prov_secret) phải được nhập thủ công vào NVS trước, hoặc flash cứng vào firmware.

---

## Flow chi tiết `tb_provision_device()`

```
┌─────────────────────────────────────────────────────┐
│ 1. Đọc MAC address WiFi STA                         │
│    → Tạo device name: "cam-AABBCCDDEE"              │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│ 2. Xây JSON body:                                   │
│    {                                                │
│      "deviceName":            "cam-AABBCCDDEE",     │
│      "provisionDeviceKey":    "<prov_key>",         │
│      "provisionDeviceSecret": "<prov_secret>",      │
│      "credentialsType":       "ACCESS_TOKEN"        │
│    }                                                │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│ 3. HTTP POST → TB_PROVISION_URL                     │
│    http://<HOST>:8080/api/v1/provision              │
│    Content-Type: application/json                   │
│    Timeout: 15s                                     │
└────────────────────────┬────────────────────────────┘
                         │
              ┌──────────┴──────────┐
          HTTP 200               HTTP 4xx/5xx
              │                      │
              ▼                      ▼
┌──────────────────────┐   ┌──────────────────────────┐
│ Parse response JSON: │   │ Log lỗi, led_set(cam,0,0)│
│ "credentialsValue"   │   │ → MQTT task thử lại 3s   │
│   hoặc "accessToken" │   └──────────────────────────┘
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ cfg->token = token   │
│ app_config_save(cfg) │  ← Lưu NVS
│ mqtt_client_create() │  ← MQTT kết nối ngay
└──────────────────────┘
```

---

## Retry tự động trong MQTT task

Nếu MQTT mất kết nối và không có token hợp lệ, `mqtt_task` sẽ **tự retry provisioning** mỗi 3 giây:

```
mqtt_task:
  while (running):
    if (!connected && has_prov_credentials):
      prov_attempts++
      tb_provision_device()  ← thử mỗi 3s
    receive telemetry queue ...
```

---

## Cấu hình Provisioning trên ThingsBoard

### Bước 1: Tạo Device Profile với Provisioning
1. ThingsBoard UI → **Device Profiles** → New Profile
2. Tab **Device provisioning** → chọn **Allow to create new devices**
3. Copy **Provision device key** và **Provision device secret**

### Bước 2: Nhập credentials vào firmware
Trong `platformio.ini`, thêm build flag (hoặc nhập trực tiếp qua NVS tool):
```ini
; Chưa có trong build flags — dùng NVS flash tool hoặc custom main.c
; Hoặc hardcode tạm cho dev:
-DPROV_KEY=\"your_prov_key\"
-DPROV_SECRET=\"your_prov_secret\"
```

Hoặc ghi thủ công vào NVS qua `idf.py` monitor:
```
nvs_set prov_key str <your_prov_key>
nvs_set prov_secret str <your_prov_secret>
```

---

## Sau khi provisioning thành công

ThingsBoard sẽ:
- Tạo Device mới tên `cam-<MAC>` trong device list
- Gán access token → được lưu trong `cfg.token`
- Device mới có thể gửi telemetry và nhận RPC

### Client Attributes tự động gửi sau khi MQTT kết nối:
```json
{
  "Model": "GOOUUU Tech ESP32-S3-CAM N16R8",
  "fw_version": "1.0.0",
  "camera_id": 1,
  "mac": "AA:BB:CC:DD:EE:FF",
  "idf_ver": "v5.3.1"
}
```

---

## Factory Reset (xóa token để re-provision)

3 cách:
1. **Giữ nút BOOT > 3 giây** → `app_config_clear()` → reboot
2. **ThingsBoard RPC** `factoryReset` → firmware tự xóa NVS + reboot
3. **ThingsBoard Shared Attribute** `factory_reset = true`

---

## Files liên quan

| File | Vai trò |
|------|---------|
| `src/tb_provisioning.c` | Logic HTTP provisioning |
| `include/tb_provisioning.h` | API + TB_PROVISION_URL |
| `src/mqtt_app.c` | Auto-retry provisioning khi mất MQTT |
| `src/app_config.c` | Lưu token vào NVS |
