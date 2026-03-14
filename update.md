ESP32 là nguồn thật
backend là trung tâm đồng bộ
frontend chỉ đọc backend và tự hiện

Flow ideal nên là:

ESP32 bật lên
đọc NVS
có Wi‑Fi thì tự nối
không có Wi‑Fi thì mở provisioning portal
ESP32 có mạng rồi
mở stream local, ví dụ http://ip:81/stream
nối ThingsBoard
gọi luôn backend POST /api/cameras/provision
Backend nhận provisioning
map thiết bị theo định danh ổn định: ưu tiên device_uid/chip_id/mac, rồi mới tới tb_device_name
nếu đã có camera cũ thì update đúng row cũ
nếu chưa có thì create mới
lưu ip, stream_host, stream_port, stream_path, fw_version, last_seen_at, online=true
Frontend
không đi đăng ký camera trực tiếp
chỉ gọi backend như /api/cameras hoặc /api/dashboard/cameras
thấy camera mới là tự hiện lên web
Sau đó ESP32 heartbeat định kỳ
ví dụ mỗi 5s = với settung của kia thingboard á đồng bộ với kia luôn đi gọi backend hoặc publish MQTT
backend chỉ update last_seen_at, online=true
nếu quá 60-90s không thấy heartbeat thì backend tự coi là offline
Đó mới là flow scale chuẩn.

Nghĩa là với case bạn nói:

nạp code hôm nay
1 năm sau cắm điện lại
thiết bị tự nối Wi‑Fi
tự nối ThingsBoard
tự gọi backend provision
backend tự nhận ra “à đây là con cũ”
update IP/stream/runtime mới
web tự hiện lại đúng camera đó