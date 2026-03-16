# 04 - ThingsBoard MQTT

## 1. Vai trò của ThingsBoard

ThingsBoard (TB) phục vụ như một Device Management Layer:

- **Identity**: Cấp Access Token cho thiết bị qua Provisioning Key/Secret.
- **Control**: Nhận lệnh RPC (Reboot, OTA, Config) từ Dashboard.
- **Config**: Đồng bộ các thông số Camera (Resolution, Quality) qua Shared Attributes.
- **Telemetry**: Giám sát sức khỏe thiết bị (RSSI, RAM, CPU Temp) theo thời gian thực.

## 2. Luồng hoạt động chính

1. **Boot**: Load config từ NVS.
2. **WiFi**: Kết nối mạng.
3. **Identity**: Nếu chưa có token, gọi TB API để lấy token.
4. **MQTT**: Kết nối và subscribe vào các sub-topic của TB.
5. **Runtime**: Gửi telemetry định kỳ và lắng nghe lệnh điều khiển.

Tham khảo chi tiết:
- [MQTT & RPC Specs](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/03_MQTT_ATTRIBUTES_RPC.md)
- [OTA & Firmware Lifecycle](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/04_OTA_AND_FIRMWARE_LIFECYCLE.md)
