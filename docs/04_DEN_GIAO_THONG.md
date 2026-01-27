# Hướng Dẫn Cài Đặt ESP32 Đèn Giao Thông

## Yêu Cầu Phần Cứng

- ESP32 DevKit (bất kỳ board nào)
- 3x LED (Đỏ, Vàng, Xanh)
- 3x Điện trở 220Ω
- 2x Nút nhấn
- 2x Điện trở pull-up 10kΩ
- Breadboard + dây jumper
- Nguồn 5V

## Sơ Đồ Đấu Nối

### LEDs

| LED | GPIO | Điện trở | GND |
|-----|------|----------|-----|
| Đỏ | GPIO 25 | 220Ω | GND |
| Vàng | GPIO 26 | 220Ω | GND |
| Xanh | GPIO 27 | 220Ω | GND |

### Buttons

| Button | GPIO | Pull-up | VCC |
|--------|------|---------|-----|
| Emergency Red | GPIO 32 | 10kΩ | 3.3V |
| Emergency Green | GPIO 33 | 10kΩ | 3.3V |

**Lưu ý**: Buttons dùng INPUT_PULLUP nội bộ, không cần điện trở ngoài.

## Cài Đặt Firmware

### 1. Mở Project

```bash
cd esp32-traffic-light
```

### 2. Cấu Hình

Sửa `include/config.h`:

```cpp
// ⚠️ ĐỔI TOKEN TỪ THINGSBOARD
#define DEVICE_TOKEN "YOUR_TRAFFIC_LIGHT_TOKEN"

// Timing (milliseconds)
#define RED_DURATION 7000      // 7 giây
#define YELLOW_DURATION 2000   // 2 giây
#define GREEN_DURATION 5000    // 5 giây

// GPIO Pins
#define RED_PIN 25
#define YELLOW_PIN 26
#define GREEN_PIN 27
#define BUTTON_RED 32
#define BUTTON_GREEN 33
```

### 3. Upload Firmware

```bash
pio run -t upload
```

## Cấu Hình WiFi

1. Sau khi upload, ESP32 tạo WiFi AP: **ESP32-TrafficLight**
2. Kết nối bằng điện thoại/laptop
3. Trình duyệt tự mở captive portal
4. Nhập WiFi credentials
5. Click "Save"

## Cấu Hình ThingsBoard

### 1. Tạo Device

**ThingsBoard → Devices → Add Device**

```
Name: TrafficLight_001
Device Profile: traffic_light
```

### 2. Copy Access Token

Click vào device → **Copy access token**

Paste vào `config.h`:
```cpp
#define DEVICE_TOKEN "eyJhbGciOiJIUzUxMiJ9..."
```

### 3. Set Shared Attributes

**Devices → TrafficLight_001 → Attributes → Shared**

```json
{
  "traffic_light_id": 1,
  "red_duration": 7000,
  "yellow_duration": 2000,
  "green_duration": 5000
}
```

## Hoạt Động

### Chế Độ Bình Thường

Đèn tự động chuyển theo chu kỳ:

```
ĐỎ (7s) → XANH (5s) → VÀNG (2s) → ĐỎ
```

### Chế Độ Khẩn Cấp

**Nút 1 (Emergency Red)**:
- Ấn lần 1: Chuyển sang ĐÈN ĐỎ (cố định)
- Ấn lần 2: Về chế độ bình thường

**Nút 2 (Emergency Green)**:
- Ấn lần 1: Chuyển sang ĐÈN XANH (cố định)
- Ấn lần 2: Về chế độ bình thường

### RPC Commands (ThingsBoard)

**ThingsBoard → Devices → TrafficLight_001 → RPC**

**Set Normal Mode**:
```json
{
  "method": "setNormalMode",
  "params": {}
}
```

**Set Emergency Red**:
```json
{
  "method": "setEmergencyRed",
  "params": {}
}
```

**Set Emergency Green**:
```json
{
  "method": "setEmergencyGreen",
  "params": {}
}
```

## Telemetry

ESP32 publish lên ThingsBoard mỗi khi đèn đổi trạng thái:

```json
{
  "traffic_light_state": "red",
  "operation_mode": "normal",
  "uptime_sec": 12345
}
```

## Đồng Bộ Với ESP32-CAM

### Cách 1: MQTT Direct

ESP32-CAM subscribe topic:
```
v1/devices/me/attributes
```

Khi Traffic Light publish `traffic_light_state`, ESP32-CAM nhận và bắt đầu chụp nếu `red`.

### Cách 2: ThingsBoard Rule Chain

**Rule Chain**: Traffic Light State → Camera Trigger

1. **Node 1**: Script
   ```javascript
   if (msg.traffic_light_state === 'red') {
       return {msg: msg, metadata: metadata, msgType: "trigger_camera"};
   }
   ```

2. **Node 2**: RPC Call to Camera
   ```json
   {
     "method": "startCapture",
     "params": {}
   }
   ```

## Serial Monitor

```
========================================
🚦 ESP32 Đèn Giao Thông
========================================

[WiFi] ✅ Đã kết nối
[WiFi] IP: 192.168.1.101
[MQTT] Đang kết nối ThingsBoard...
[MQTT] ✅ Đã kết nối!
[Light] 🔴 ĐỎ (7s)

[Light] 🟢 XANH (5s)

[Light] 🟡 VÀNG (2s)

[Light] 🔴 ĐỎ (7s)

[Button] 🔴 Chuyển sang khẩn cấp: ĐÈN ĐỎ
[Button] 🔴 Từ khẩn cấp đỏ -> Bình thường
```

## Xử Lý Sự Cố

### LED không sáng

**Nguyên nhân**: GPIO sai hoặc điện trở quá lớn

**Giải pháp**:
1. Verify GPIO pins trong code
2. Kiểm tra kết nối LED
3. Dùng điện trở 220Ω (không lớn hơn)
4. Test LED trực tiếp với 3.3V

### MQTT không kết nối

**Nguyên nhân**: Token sai

**Giải pháp**:
1. Copy lại token từ ThingsBoard
2. Verify không có khoảng trắng thừa
3. Kiểm tra ThingsBoard server online

### Nút nhấn không hoạt động

**Nguyên nhân**: Debounce hoặc pull-up

**Giải pháp**:
1. Verify `INPUT_PULLUP` trong code
2. Tăng debounce time:
   ```cpp
   #define BUTTON_DEBOUNCE_MS 1000  // 1 giây
   ```

### Timing không đúng

**Nguyên nhân**: Config sai

**Giải pháp**:
Sửa trong `config.h`:
```cpp
#define RED_DURATION 7000      // milliseconds
#define YELLOW_DURATION 2000
#define GREEN_DURATION 5000
```

## Tính Năng Nâng Cao

### 1. Đồng Bộ Nhiều Đèn

Dùng ThingsBoard Device Group để điều khiển nhiều đèn cùng lúc.

### 2. Schedule

ThingsBoard Scheduler để thay đổi timing theo giờ:
- Giờ cao điểm: Đỏ 10s, Xanh 8s
- Giờ thấp điểm: Đỏ 5s, Xanh 3s

### 3. Traffic Density

Dùng sensor đếm xe, tự động điều chỉnh timing.

## Maintenance

### Update Firmware

1. Sửa code
2. Build: `pio run`
3. Upload: `pio run -t upload`

### Reset WiFi

Uncomment trong code:
```cpp
void setup() {
    // ...
    WiFiManager wm;
    wm.resetSettings();  // ← Thêm dòng này
    // ...
}
```

Upload lại, sau đó comment và upload lần nữa.

## Tích Hợp Với Hệ Thống

```
ESP32 Traffic Light
    ↓ MQTT
ThingsBoard
    ↓ Rule Chain
ESP32-CAM (nhận signal đèn đỏ)
    ↓ HTTP POST
Backend (detect vi phạm)
    ↓ Save
Database
    ↓ Display
Web Dashboard
```

## Best Practices

- ✅ Dùng nguồn 5V ổn định (không dùng USB)
- ✅ Kiểm tra LED trước khi đấu vào ESP32
- ✅ Test buttons riêng lẻ
- ✅ Monitor serial để debug
- ✅ Backup token ThingsBoard
