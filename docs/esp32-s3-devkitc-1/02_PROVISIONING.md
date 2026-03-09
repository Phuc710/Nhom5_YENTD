# 02 - ThingsBoard Provisioning

## Tong quan

Provisioning la buoc board xin `access_token` tu ThingsBoard de dung cho MQTT.

Token duoc luu vao NVS. Boot sau dung lai token cu, khong can provision lai, tru khi:

- NVS chua co token
- operator goi `reprovision`
- operator xoa token cu
- factory reset

## Khi nao firmware chay provisioning

### Boot path

1. `main.c` doc `app_config`
2. neu `cfg.token` rong va co du `provisioning_key + provisioning_secret`
3. goi `tb_provision_device(&cfg)`
4. neu thanh cong, token duoc luu vao NVS
5. MQTT se duoc khoi tao o buoc sau cua boot sequence

### MQTT retry path

`mqtt_task` se thu provisioning lai moi `3s` khi:

- MQTT chua khoi tao thanh cong
- hoac da mat ket noi va dang co provisioning credentials

Neu provisioning thanh cong trong path nay:

- token moi duoc luu vao `s_cfg.token`
- firmware goi `mqtt_client_create(s_cfg.token)` ngay

## Request provisioning thuc te

Firmware tao `deviceName` tu MAC WiFi STA:

```text
cam-AABBCCDDEEFF
```

Body POST len `TB_PROVISION_URL`:

```json
{
  "deviceName": "cam-AABBCCDDEEFF",
  "provisionDeviceKey": "....",
  "provisionDeviceSecret": "....",
  "credentialsType": "ACCESS_TOKEN"
}
```

## Response ma firmware parse

Firmware parse thu cong 2 key co the co:

- `credentialsValue`
- `accessToken`

Sau khi parse thanh cong:

- `cfg->token` duoc cap nhat
- `app_config_save(cfg)` luu token vao NVS

## Sync backend sau khi co token va MQTT on dinh

Sau `MQTT_EVENT_CONNECTED`, firmware tu goi:

```text
POST /api/cameras/provision
```

Body sync:

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

Backend se:

- upsert `camera_provisioning`
- tao camera neu chua ton tai
- cap nhat `status=active`
- cap nhat `stream_url` tu `ip_address` khi phu hop

## Client attributes va runtime snapshot sau khi MQTT ket noi

Firmware khong chi gui `Model/fw_version/camera_id/mac/idf_ver` nhu tai lieu cu.
Hien tai firmware gui them:

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

## Reprovision va factory reset

### Reprovision

Cac cach kich hoat:

- RPC `reprovision`
- shared attribute `reprovision = true`
- shared attribute `clear_token = true`

Firmware se:

1. goi `app_config_clear_token()`
2. giu lai WiFi va provisioning credentials
3. reboot
4. boot lai va xin token moi

### Factory reset

Cac cach kich hoat:

- giu nut BOOT > 3 giay
- RPC `factoryReset`
- shared attribute `factory_reset = true`

Firmware se xoa toan bo NVS va khoi dong lai.
