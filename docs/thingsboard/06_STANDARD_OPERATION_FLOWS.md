# Cac luong chuan end-to-end

## 1. Luong A: boot binh thuong da co token

1. ESP32 boot
2. doc NVS
3. co token nen bo qua provisioning
4. WiFi connect
5. MQTT connect ThingsBoard
6. request shared attributes
7. publish runtime snapshot
8. sync provisioning ve backend
9. backend cap nhat camera active, IP va stream URL
10. camera task va uploader task hoat dong

## 2. Luong B: boot lan dau chua co token

1. ESP32 boot
2. token rong
3. `tb_provision_device()` chay o boot path
4. ThingsBoard tra `access_token`
5. firmware luu token vao NVS
6. sau do `mqtt_task` duoc khoi tao
7. MQTT connect
8. firmware sync provisioning ve backend
9. backend tao hoac update camera va provisioning

## 3. Luong C: mat MQTT hoac chua khoi tao MQTT

1. `MQTT_EVENT_DISCONNECTED` xay ra hoac MQTT chua init thanh cong
2. `mqtt_task` danh dau can thu provisioning lai
3. moi 3 giay, neu co provisioning credentials:
   - thu provisioning lai
   - neu thanh cong, tao lai MQTT client
4. khi MQTT connect lai, firmware publish runtime snapshot
5. firmware sync provisioning ve backend lai

## 4. Luong D: OTA chuan

1. ThingsBoard dat `fw_title + fw_version` hoac `ota_url`
2. firmware nhan attributes
3. neu version khac, goi `start_ota()`
4. firmware publish `fw_state`
5. OTA download va flash
6. reboot
7. `main.c` xac nhan firmware hop le neu dang `PENDING_VERIFY`
8. MQTT connect lai
9. sync provisioning ve backend voi `fw_version` moi

## 5. Luong E: upload va vi pham

1. den do: firmware upload frame len backend
2. backend detect va buffer
3. den khong do: firmware khong upload full frame, chi heartbeat
4. chuyen `do -> xanh`: firmware goi `/api/finalize`
5. backend chot buffer va tao vi pham neu du dieu kien

## 6. Luong F: dashboard canh sat

1. firmware online
2. backend nhan provisioning sync, upload hoac heartbeat
3. backend cap nhat `last_seen_at`, `online`, `ip_address`, `stream_url`
4. dashboard goi `/api/dashboard/*`
5. web hien thi camera, stream URL, firmware, IP, violations

## 7. Nguyen tac match lau dai

- ThingsBoard dieu phoi thiet bi
- firmware thi hanh tren board
- backend chuan hoa du lieu cho web
- khoa match chinh la `camera_id + mac_address + tb_device_name`
- `ip_address` la du lieu dong, chi dung cho stream va debug
