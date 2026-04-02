# 07 - Health Telemetry (Giám sát sức khỏe)

Hệ thống giám sát sức khỏe thiết bị định kỳ (mặc định 5s) và gửi dữ liệu lên ThingsBoard & Backend. Dữ liệu này là cơ sở để vẽ biểu đồ Dashboard và cảnh báo.

## 1. Danh sách các trường Health (Chuẩn)

| Trường | Mô tả | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `online` | `true`/`false` | Trạng thái sống/chết. |
| `device_state` | `booting`, `running`, `degraded`, `ota`, `error` | Trạng thái hệ thống chi tiết. |
| `light_state` | `RED`, `YELLOW`, `GREEN`, `OFF` | Trạng thái đèn giao thông |
| `wifi_rssi` | Cường độ sóng (dBm) | Đánh giá độ ổn định kết nối không dây. |
| `cpu_temp` | Nhiệt độ chip (°C) | Cảnh báo quá nhiệt (ngắt camera nếu > 85°C). |
| `free_heap` | RAM khả dụng (Bytes) | Phát hiện rò rỉ bộ nhớ (Memory Leak). |
| `uptime_s` | Thời gian chạy (giây) | Theo dõi độ ổn định (uptime) theo thời gian. |
| `camera_ok` | `true`/`false` | Kiểm tra phần cứng camera (Cáp lỏng, lỗi I2C). |

## 2. Cơ chế Circuit Breaker & Degraded Mode
Nếu Backend HTTP sập hoặc phản hồi quá chậm (> 3 lần), ESP32 tự động chuyển sang `DEGRADED` mode.
- Giãn chu kỳ Heartbeat lên **60s** để bảo vệ tài nguyên mạng.
- Hệ thống tự động phục hồi về `running` ngay khi kết nối Backend thành công trở lại.

## 3. Luồng xử lý dữ liệu
1. **Device**: Thu thập dữ liệu qua `health_telemetry_t` struct.
2. **Transport**: Gửi qua MQTT (ThingsBoard) và REST (Backend Heartbeat).
3. **Backend**: Đồng bộ hóa `light_state` và `device_state` vào Database.

---
*Ghi chú: Mọi thay đổi về field name trong firmware cần được cập nhật đồng bộ trong `backend/models/camera.py`.*
