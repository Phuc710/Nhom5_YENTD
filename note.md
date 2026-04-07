
thingsboard healthy ở http://localhost:9090
mosquitto chạy ở localhost:1888
backend healthy ở http://localhost:8000/health


cd C:\Users\Phucc\Desktop\ytd
docker compose up -d

cd frontend
python -m http.server 8080

C:\Users\Phucc\.platformio\penv\Scripts\platformio.exe run -e esp32-s3-devkitc-1 --target upload


  netsh advfirewall firewall show rule name=all | findstr :8000



Plan Chuẩn

WiFi self-test
Kết nối STA, verify IP, verify reach được broker/backend.
Nếu fail thì chưa active gì cả, reboot hoặc retry.
Hiện phần này ở main.c (line 254).
Cloud auth/reconnect
Nếu đã có token: thử reconnect MQTT ThingsBoard trước, không provision lại bừa.
Nếu không có token: mới gọi ThingsBoard device provisioning để lấy token mới.
Chỗ này ở mqtt_app.c (line 903).
Stream endpoint up
Khi MQTT ok rồi thì mở /, /snapshot, /stream để backend có cái mà pull.
Chỗ này ở main.c (line 301) và stream_server.c (line 161).
Backend sync/provision
Sau khi stream đã sống, ESP32 gọi backend /api/cameras/provision.
Backend phải trả về dữ liệu canonical của camera, đặc biệt là camera_id.
ESP32 phải parse response, cập nhật camera_id, lưu NVS, rồi mới coi là synced.
Đây là bước cần làm tiếp trong backend_sync.c (line 174).
Publish state/telemetry
Sau khi backend synced mới cho traffic light và các task user-facing chạy.
Khi đó telemetry đèn mới đúng camera.
Chỗ gating hiện ở main.c (line 314).
Runtime reconnect
Mất mạng: dừng coi là ready.
Có mạng lại: test lại WiFi -> MQTT -> stream -> backend sync.
Chỉ pass hết mới active lại traffic/logic.
Đây là phần cần làm tiếp cho “reconnect all” hoàn chỉnh.
ESP32 Gửi Gì Khi Boot/Reconnect

1. ThingsBoard device provisioning

Chỉ dùng khi chưa có token.
Payload hiện tại ở tb_provisioning.c (line 138):
deviceName
provisionDeviceKey
provisionDeviceSecret
credentialsType=ACCESS_TOKEN
2. ThingsBoard client attributes khi MQTT connect

Gửi ở mqtt_app.c (line 215)
device_model
device_name
tb_device_name
mac_address
fw_version
idf_ver
location
reset_reason
wifi_ssid
resolution
ip_address
stream_url
stream_scheme
stream_host
stream_port
stream_path
stream_snapshot_path
backend_url
device_state
backend_sync
3. Backend HTTP provision

Gửi ở backend_sync.c (line 194)
camera_id
camera_name
tb_device_name
mac_address
ip_address
stream_url
location
4. MQTT telemetry runtime

Gửi ở mqtt_app.c (line 803)
Health:
free_heap, min_free_heap, wifi_rssi, uptime_s, camera_ok, mqtt_connected, backend_degraded, wifi_disconnect_count, device_state, last_seen_ts, light_state, cpu_temp
Traffic:
light_state, remain_sec, operation_mode, device_state, rssi, free_heap, tl_state_ms, phase_duration_ms, red_on, yellow_on, green_on
Ưu Tiên Sửa Tiếp

Parse JSON response của backend /api/cameras/provision để cập nhật camera_id thật vào firmware và NVS.
Chỉ set backend_sync = synced sau khi parse và apply response thành công.
Thêm state machine reconnect chuẩn: mất online thì hạ ready, online lại thì chạy lại full self-test.
Sau đó mới xử lý MJPEG parser/backend pull stream.
Kết luận
Đúng, phải đồng bộ backend trước rồi mới cho đèn giao thông chạy. Nếu camera_id backend là 2 mà firmware vẫn gửi telemetry với 1 thì hệ thống sẽ lệch mãi. Bước sửa đúng thứ tự là: sync ID backend trước, rồi mới fix stream parser, rồi hoàn thiện reconnect all.

Nếu muốn, mình làm tiếp ngay bước 1: sửa backend_sync.c (line 174) để parse response backend và cập nhật camera_id chuẩn.


