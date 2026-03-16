# 07 - Health Telemetry (Giám sát sức khỏe)

Hệ thống giám sát sức khỏe thiết bị định kỳ (mặc định 5s) và gửi dữ liệu lên ThingsBoard & Backend. Dữ liệu này là cơ sở để vẽ biểu đồ Dashboard và cảnh báo.

## 1. Danh sách các trường Health (Chuẩn)

| Trường | Mô tả | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `online` | `true`/`false` | Trạng thái sống/chết của thiết bị. |
| `device_state` | `running`, `ota`, `error` | Trạng thái hoạt động chi tiết. |
| `light_mode` | `red`, `green`, `yellow`, `off` | Trạng thái đèn giao thông hiện tại. |
| `wifi_rssi` | Cường độ sóng (dBm) | Đánh giá độ ổn định kết nối không dây. |
| `cpu_temp` | Nhiệt độ chip (°C) | Cảnh báo quá nhiệt (ngắt camera nếu > 85°C). |
| `free_heap` | RAM khả dụng (Bytes) | Phát hiện rò rỉ bộ nhớ (Memory Leak). |
| `uptime_s` | Thời gian chạy (giây) | Theo dõi độ ổn định (uptime) theo thời gian. |
| `camera_ok` | `true`/`false` | Kiểm tra phần cứng camera (Cáp lỏng, lỗi I2C). |

## 2. Luồng xử lý dữ liệu
1. **Device**: Thu thập dữ liệu qua `health_telemetry_t` struct.
2. **Transport**: Gửi qua MQTT (ThingsBoard) và REST (Backend Heartbeat).
3. **Backend**: Chuẩn hóa key (ví dụ: `Light_Mode` ➔ `light_mode`) và lưu vào Supabase.
4. **Web**: Hiển thị biểu đồ thời gian thực.

---
*Ghi chú: Mọi thay đổi về field name trong firmware cần được cập nhật đồng bộ trong `backend/models/camera.py`.*
