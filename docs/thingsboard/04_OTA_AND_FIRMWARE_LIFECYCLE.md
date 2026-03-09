# OTA Và Vòng Đời Firmware

## 1. OTA trong hệ thống này do ai điều phối

OTA hiện do ThingsBoard điều phối, không phải backend.

Backend chỉ nên:

- lưu `fw_version` mới nhất sau khi sync provisioning hoặc heartbeat mở rộng
- hiển thị version cho dashboard cảnh sát

## 2. Các cách kích hoạt OTA đang có trong code

### Cách 1: Shared attributes `fw_title + fw_version`

Khi firmware nhận:

- `fw_title`
- `fw_version`

thì nó sẽ so sánh với version hiện tại.

Nếu khác version:

- tự build URL:
  `THINGSBOARD_BASE_URL/api/v1/<token>/firmware?title=...&version=...`
- gọi `start_ota()`

### Cách 2: Shared attributes `ota_url` hoặc `fw_url`

Nếu có URL trực tiếp và khác URL cũ:

- firmware gọi `start_ota(url)`

### Cách 3: RPC `startOTA`

ThingsBoard có thể gọi RPC:

```json
{
  "method": "startOTA",
  "params": {
    "url": "http://server/fw.bin"
  }
}
```

## 3. Luồng OTA thực tế

1. MQTT nhận attribute hoặc RPC.
2. Firmware gọi `start_ota()`.
3. Tạo `ota_task`.
4. `ota_task` dùng `esp_https_ota()`.
5. Firmware publish `fw_state`.
6. Thành công thì reboot.
7. Sau boot mới, `main.c` gọi `esp_ota_mark_app_valid_cancel_rollback()`.

## 4. Các trạng thái OTA quan trọng

- `DOWNLOADING`
- `UPDATED`
- `FAILED`

Các trạng thái này đang được publish lên ThingsBoard qua client attributes.

## 5. Rollback protection

Theo [`main.c`](/c:/Users/Phucc/Desktop/ytd/esp32-s3-devkitc-1/src/main.c):

- nếu boot từ image OTA mới ở trạng thái `PENDING_VERIFY`
- firmware sẽ mark image hợp lệ

Điều này giúp:

- tránh brick thiết bị khi OTA lỗi
- giữ được cơ chế rollback của ESP-IDF

## 6. Match firmware version toàn hệ thống

Để match all tốt:

- ThingsBoard là nơi phát OTA
- firmware là nơi xác nhận version chạy thật
- backend là nơi lưu version để web cảnh sát xem

Flow chuẩn:

1. TB phát OTA.
2. Board OTA và reboot.
3. Board MQTT connect lại.
4. Board publish `fw_version` mới.
5. Backend sync lại `fw_version`.

Hiện trạng:

- bước 1 đến 4 đã có trong firmware
- bước 5 mới có contract backend, chưa có bridge tự động từ firmware sang backend

## 7. Kết luận

OTA chuẩn của hệ thống này phải hiểu là:

- ThingsBoard điều phối
- firmware thi hành
- backend chỉ quan sát và hiển thị

Không nên để backend trở thành nơi phát OTA chính nếu muốn giữ kiến trúc hiện tại đơn giản và ổn định.
