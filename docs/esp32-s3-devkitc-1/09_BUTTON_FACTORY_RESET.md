# 09 - Button And Factory Reset

## Hành vi hiện tại

`button_task` theo dõi nút `BOOT` tại `GPIO 0`.

Rule:

- giữ hơn `3000 ms` để kích hoạt factory reset
- nhấn nhanh thì bỏ qua

## Feedback LED

Trong lúc giữ:

- LED đỏ chớp theo chu kỳ

Khi đủ thời gian:

- LED đỏ chớp nhanh `5` lần
- xóa toàn bộ NVS
- reboot

## Factory reset xóa gì

Factory reset gọi `app_config_clear()` và đưa thiết bị về trạng thái NVS trống.

Nghĩa là các config runtime lưu trong NVS sẽ mất.

## Sau reset

- board reboot
- thiết bị quay lại trạng thái cấu hình ban đầu
- nếu chưa có WiFi, firmware sẽ đi vào flow cấu hình lại

## Source of truth

- [button_task.c](../../esp32-s3-devkitc-1/main/button_task.c)
- [app_config.c](../../esp32-s3-devkitc-1/main/app_config.c)
