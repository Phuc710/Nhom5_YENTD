# Provisioning Và Định Danh Thiết Bị

## 1. Mục tiêu của provisioning

Provisioning là bước đăng ký board mới lên ThingsBoard để lấy `access_token` dùng cho MQTT.

Theo code hiện tại:

- logic nằm ở [`tb_provisioning.c`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/src/tb_provisioning.c)
- khai báo nằm ở [`tb_provisioning.h`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/include/tb_provisioning.h)
- boot sequence gọi provisioning ở [`main.c`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/src/main.c)
- bước sync backend được xử lý ở [`mqtt_app.c`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/src/mqtt_app.c)

## 2. Khi nào firmware chạy provisioning

Firmware kiểm tra trong `main.c`:

- nếu NVS chưa có `token`
- và có đủ `provisioning_key + provisioning_secret`

thì sẽ gọi:

`tb_provision_device(&cfg)`

Nếu thất bại lúc boot, `mqtt_task` sẽ retry provisioning mỗi `3 giây`.

## 3. Request provisioning thực tế

Firmware tự tạo `deviceName` từ MAC:

`cam-<MAC_HEX>`

Ví dụ:

`cam-AABBCCDDEEFF`

Body gửi lên `TB_PROVISION_URL` có dạng:

```json
{
  "deviceName": "cam-AABBCCDDEEFF",
  "provisionDeviceKey": "....",
  "provisionDeviceSecret": "....",
  "credentialsType": "ACCESS_TOKEN"
}
```

## 4. Response mà firmware đang parse

Code hiện parse thủ công 2 key có thể có:

- `credentialsValue`
- `accessToken`

Sau khi parse thành công:

- token được ghi vào `cfg->token`
- token được lưu lại vào NVS bằng `app_config_save()`

## 5. Dữ liệu được giữ trong NVS

Cấu trúc nằm ở [`app_config.h`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/include/app_config.h).

Những field liên quan ThingsBoard:

- `token`
- `provisioning_key`
- `provisioning_secret`
- `frames_per_upload`

Điểm cần nhớ:

- `token` là dữ liệu runtime lâu dài
- `provisioning_key` và `provisioning_secret` là dữ liệu cấp phát
- `factory reset` sẽ xóa NVS, đồng nghĩa với việc thiết bị phải provisioning lại

## 6. Định danh chuẩn của một board

Board nên được hiểu theo 5 lớp:

1. phần cứng thật: `mac_address`
2. nghiệp vụ: `camera_id`
3. ThingsBoard logic: `tb_device_name`
4. ThingsBoard access: `access_token`
5. mạng nội bộ: `ip_address`

## 7. Chuẩn sync sau provisioning

Để match toàn hệ thống tốt nhất, sau khi MQTT ổn định firmware sẽ tự gọi:

`POST /api/cameras/provision`

Body chuẩn:

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

Hành vi hiện tại:

- firmware sync ngay sau `MQTT_EVENT_CONNECTED`
- nếu ThingsBoard cập nhật lại `camera_id`, firmware sẽ đánh dấu sync lại
- backend upsert `camera_provisioning`
- backend cập nhật `status=active`
- backend tự sinh lại `stream_url` từ IP nếu camera đang dùng URL tự quản lý

## 8. Kết luận

Provisioning chuẩn không chỉ là “lấy token”.

Provisioning chuẩn của cả hệ thống hiện đã làm đủ:

1. lấy token từ ThingsBoard
2. lưu token vào NVS
3. MQTT connect bằng token
4. sync danh tính thiết bị về backend
5. đồng bộ lại IP/stream khi board đổi mạng
