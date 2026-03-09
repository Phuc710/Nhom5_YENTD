# Kiến trúc Và Quy Tắc Match

## 1. Mô hình tổng thể

```text
ESP32-S3-DevKitC-1
    -> HTTP provisioning -> ThingsBoard
    -> MQTT telemetry / RPC -> ThingsBoard
    -> HTTP upload frame -> Backend
    -> HTTP sync provisioning -> Backend
    -> HTTP stream nội bộ -> backend hoặc web nội bộ

ThingsBoard
    -> cấp token
    -> giữ shared attributes
    -> nhận telemetry
    -> gửi RPC
    -> quản lý OTA

Backend
    -> lưu camera và camera_provisioning
    -> tự cập nhật stream_url từ IP camera khi cần
    -> nhận upload ảnh
    -> lưu bằng chứng vi phạm
    -> làm API cho dashboard cảnh sát

Web cảnh sát
    -> chỉ gọi backend
    -> không dùng access token của ThingsBoard
```

## 2. Các lớp định danh chuẩn

### `camera_id`

Là khóa nghiệp vụ của camera trong toàn hệ thống.

Dùng cho:

- backend API
- database
- dashboard cảnh sát
- mapping zone và vi phạm

### `mac_address`

Là khóa phần cứng thật của board ESP32.

Dùng cho:

- xác minh đúng thiết bị vật lý
- phát hiện thay đổi IP
- ràng buộc `camera_id` với đúng board

### `tb_device_id`, `tb_device_name` và `access_token`

Là khóa của lớp ThingsBoard.

Dùng cho:

- kết nối MQTT
- provisioning
- OTA
- đối chiếu thiết bị giữa firmware và backend

Trong code hiện tại:

- firmware tự sinh `tb_device_name = cam-<MAC_HEX>`
- payload sync backend gửi cả `tb_device_id` và `tb_device_name` theo cùng giá trị này
- `access_token` là token thật để MQTT và OTA hoạt động

### `ip_address`

Là dữ liệu động theo mạng nội bộ.

Dùng cho:

- stream nội bộ
- backend cập nhật `stream_url`
- debug mạng

Không dùng `ip_address` làm khóa định danh chính vì IP có thể đổi sau mỗi lần boot hoặc đổi WiFi.

## 3. Quy tắc match chuẩn nhất

Một camera chuẩn phải được match theo chuỗi sau:

`camera_id <-> mac_address <-> tb_device_name/tb_device_id <-> access_token <-> ip_address`

Trong đó:

- `camera_id` là khóa nhìn thấy ở frontend/backend
- `mac_address` là khóa tin cậy nhất ở tầng thiết bị
- `tb_device_name` là tên thiết bị đồng nhất giữa provisioning và backend sync
- `access_token` là khóa MQTT/OTA
- `ip_address` là bản ghi mới nhất để backend dùng cho stream nội bộ

## 4. Nguồn sự thật của từng field

| Field | Nguồn sự thật chính |
|------|----------------------|
| `camera_id` | shared attribute ThingsBoard + database backend |
| `mac_address` | firmware đọc từ ESP32 STA MAC |
| `tb_device_name` | firmware tự sinh từ MAC |
| `tb_device_id` | payload sync backend, hiện dùng cùng giá trị `tb_device_name` |
| `access_token` | provisioning + NVS |
| `ip_address` | firmware khi thiết bị online |
| `fw_version` | firmware publish sau boot / sau OTA |

## 5. Trạng thái code hiện tại

Đã có trong code:

- firmware provisioning lấy token từ ThingsBoard
- firmware MQTT connect bằng token
- firmware publish client attributes và telemetry
- firmware tự sync provisioning về backend sau khi MQTT kết nối
- firmware tự sync lại khi `camera_id` được cập nhật từ ThingsBoard
- backend có endpoint [`/api/cameras/provision`](/c:/Users/Phucc/Desktop/ytd/backend/api/cameras.py)
- backend có bảng `camera_provisioning`
- backend tự cập nhật `stream_url = http://<ip>/stream` nếu camera đang dùng URL tự sinh

Chưa nối hết trong code:

- backend hiện chưa đọc ngược telemetry từ ThingsBoard để dựng trạng thái đèn realtime cho web
- web cảnh sát chưa có proxy stream chuẩn hóa qua backend
- rule `zone + stop_line + traffic_light_state` chưa được backend triển khai đầy đủ

## 6. Luồng chuẩn nên bám

1. Board boot.
2. Nếu chưa có token thì provisioning với ThingsBoard.
3. Có token thì MQTT connect.
4. Sau khi có đủ `camera_id + mac + ip + fw + token`, firmware tự sync về backend.
5. Backend update `cameras` và `camera_provisioning`.
6. Nếu camera đang dùng stream URL tự sinh, backend cập nhật sang IP mới nhất.
7. Web cảnh sát chỉ xem dữ liệu từ backend.

Đây là cách match ổn định nhất cho môi trường `laptop + ESP32 test thường xuyên`.
