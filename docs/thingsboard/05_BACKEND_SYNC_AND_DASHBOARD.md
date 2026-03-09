# Backend Sync Và Dashboard Cảnh Sát

## 1. Backend hiện có gì cho lớp ThingsBoard

Backend đã có:

- endpoint [`POST /api/cameras/provision`](/c:/Users/Phucc/Desktop/ytd/backend/api/cameras.py)
- service sync provisioning ở [`camera_service.py`](/c:/Users/Phucc/Desktop/ytd/backend/services/camera_service.py)
- bảng `camera_provisioning`
- view `view_camera_summary`

Các field backend đang sẵn sàng lưu:

- `tb_device_id`
- `tb_device_name`
- `access_token`
- `mac_address`
- `fw_version`
- `idf_version`
- `ip_address`
- `last_seen_at`
- `online`

## 2. Mục tiêu sync đúng chuẩn

Backend phải là lớp chuẩn hóa để web cảnh sát xem dữ liệu ổn định.

Web không nên phụ thuộc trực tiếp vào:

- access token
- MQTT topic
- ThingsBoard RPC
- raw telemetry JSON

## 3. Luồng sync chuẩn nhất

### Luồng đồng bộ danh tính thiết bị

1. Board có token và đã MQTT connect.
2. Board biết `camera_id`.
3. Board biết `mac_address`, `ip_address`, `fw_version`.
4. Firmware tự gửi `POST /api/cameras/provision` cho backend.
5. Backend upsert `camera_provisioning`.
6. Backend cập nhật `status=active`.
7. Nếu `stream_url` đang là URL tự sinh từ IP cũ hoặc đang để trống, backend tự cập nhật lại `stream_url`.
8. Dashboard cảnh sát đọc từ `view_camera_summary`.

### Luồng heartbeat

Hiện tại backend cập nhật `last_seen_at` chủ yếu qua:

- `POST /api/upload`
- `POST /api/upload/heartbeat`

Điều này đủ cho dashboard cơ bản, dù chưa sync trực tiếp từ telemetry ThingsBoard.

## 4. Vai trò của ThingsBoard trong dashboard cảnh sát

ThingsBoard là nguồn dữ liệu vận hành gốc, nhưng dashboard cảnh sát nên xem qua backend.

Lý do:

- backend đã chuẩn hóa `camera_id`
- backend đã biết camera, zone, vi phạm, ảnh
- web cảnh sát chỉ cần một API duy nhất
- dễ kiểm soát bảo mật hơn

## 5. Dữ liệu nào nên đi vào web

Nên đưa vào dashboard cảnh sát:

- `camera_id`
- `camera_name`
- `location`
- `online`
- `last_seen_at`
- `ip_address`
- `fw_version`
- `stream_url`
- `violations_today`
- `violations_total`

Không nên đưa thẳng ra frontend:

- `access_token`
- `provisioning_key`
- `provisioning_secret`
- raw payload MQTT

## 6. Điểm lệch hiện tại cần ghi nhớ

Đã có:

- firmware tự sync provisioning về backend
- backend contract để sync provisioning
- backend tự cập nhật `stream_url` từ `ip_address` nếu phù hợp
- dashboard cảnh sát có namespace `/api/dashboard/*`

Chưa có hoàn chỉnh:

- backend chưa có lớp kéo telemetry từ ThingsBoard để hiển thị trạng thái đèn realtime
- stream hiện vẫn dựa vào `stream_url`, chưa có proxy stream chuẩn hóa qua backend
- backend chưa áp rule `zone + stop_line + traffic_light_state` để kết luận vi phạm hoàn chỉnh

## 7. Kết luận

Muốn match toàn hệ thống tốt thì backend phải là điểm hội tụ dữ liệu:

- nhận định danh từ firmware
- lưu mapping ThingsBoard
- cập nhật IP/stream mới nhất
- làm API duy nhất cho dashboard

Đây là lớp giúp hệ thống không bị phụ thuộc vào IP đổi hoặc cấu trúc raw của ThingsBoard.
