# Hướng Dẫn Cài Đặt ESP32-CAM

## Yêu Cầu Phần Cứng

- ESP32-CAM (AI-Thinker)
- FTDI programmer hoặc USB-TTL adapter
- Nguồn 5V 2A
- Dây jumper
- Thẻ MicroSD (tùy chọn)

## Đấu Nối Lập Trình

| FTDI | ESP32-CAM |
|------|-----------|
| 5V | 5V |
| GND | GND |
| TX | U0R |
| RX | U0T |

**⚠️ Quan trọng**: Nối GPIO0 xuống GND để vào chế độ flash

## Cài Đặt Phần Mềm

### 1. Cài PlatformIO

**VSCode Extension**:
- Mở VSCode
- Cài extension "PlatformIO IDE"
- Restart VSCode

**Hoặc CLI**:
```bash
pip install platformio
```

### 2. Mở Project

```bash
cd esp32-cam
pio init
```

### 3. Cấu Hình

Sửa `include/config.h`:

```cpp
// ⚠️ ĐỔI ĐỊA CHỈ VPS
#define BACKEND_URL "http://YOUR_VPS_IP:8000/api/upload"

// ⚠️ ĐỔI PROVISION KEYS (từ ThingsBoard)
#define PROVISION_DEVICE_KEY "your-key"
#define PROVISION_DEVICE_SECRET "your-secret"
```

### 4. Upload Firmware

```bash
# Kết nối FTDI
# GPIO0 nối GND

pio run -t upload

# Sau khi upload xong:
# - Ngắt GPIO0 khỏi GND
# - Nhấn nút RESET trên ESP32-CAM
```

## Cấu Hình Lần Đầu

### 1. Kết Nối WiFi

1. Cấp nguồn cho ESP32-CAM
2. Tìm WiFi AP: **ESP32-CAM-Setup**
3. Kết nối bằng điện thoại/laptop
4. Trình duyệt tự mở captive portal
5. Nhập WiFi credentials
6. Click "Save"

Nếu portal không tự mở:
- Vào `http://192.168.4.1` thủ công

### 2. Provisioning

Sau khi WiFi kết nối:
- ESP32 tự động provision với ThingsBoard
- Token được lưu vào NVS (non-volatile storage)
- Device xuất hiện trong ThingsBoard devices list

### 3. Kiểm Tra Hoạt Động

Mở Serial Monitor (115200 baud):

```
========================================
🚦 ESP32-CAM Vi Phạm Vượt Đèn Đỏ
========================================

[Setup] Bước 1: Khởi tạo camera...
[Camera] ✅ Initialized successfully
[Setup] Bước 2: Kết nối WiFi...
[WiFi] ✅ Đã kết nối!
[WiFi] IP: 192.168.1.100
[Setup] Bước 3: Provisioning ThingsBoard...
[Provision] ✅ Thành công!
[Setup] Bước 4: Kết nối MQTT...
[MQTT] ✅ Đã kết nối!
[Setup] Bước 5: Request shared attributes...
[Setup] Bước 6: Khởi tạo OTA update...
[OTA] ✅ OTA ready

✅ Setup hoàn tất!
```

## Cấu Hình ThingsBoard Attributes

Trong ThingsBoard dashboard:

| Attribute | Type | Default | Mô tả |
|-----------|------|---------|-------|
| `camera_id` | Integer | 1 | ID camera (1, 2, 3) |
| `capture_interval` | Integer | 1000 | Khoảng cách chụp (ms) |
| `traffic_light_state` | String | "red" | Trạng thái đèn |

**Cách set attributes**:
1. ThingsBoard → Devices → Chọn ESP32-CAM
2. Tab "Attributes"
3. Click "+" để thêm shared attribute
4. Nhập key/value
5. ESP32 tự động nhận và áp dụng

## Cấu Hình Camera

Resolution được set trong `config.h`:

```cpp
#define CAMERA_FRAME_SIZE FRAMESIZE_UXGA  // 1600x1200
#define CAMERA_JPEG_QUALITY 10  // Thấp hơn = chất lượng cao hơn
```

**Frame sizes có sẵn**:
- `FRAMESIZE_UXGA` (1600x1200) - **Khuyến nghị** cho detect biển số
- `FRAMESIZE_SXGA` (1280x1024)
- `FRAMESIZE_XGA` (1024x768)
- `FRAMESIZE_SVGA` (800x600)

## Quản Lý Bộ Nhớ

ESP32-CAM có RAM hạn chế. Code đã xử lý cleanup:

```cpp
// 1. Chụp
camera_fb_t* fb = camera_capture();

// 2. Cấp phát buffer
uint8_t* buffer = ps_malloc(size);

// 3. Sử dụng buffer...

// 4. CLEANUP (QUAN TRỌNG!)
free(buffer);           // Giải phóng buffer
camera_release(fb);     // Trả frame buffer
http.end();             // Đóng HTTP connection
```

**⚠️ Luôn cleanup theo đúng thứ tự!** Nếu không ESP32 sẽ crash sau vài lần chụp.

## OTA Update

### Cách 1: Từ ThingsBoard (Khuyến nghị)

1. **Upload firmware lên ThingsBoard**:
   - Build firmware: `pio run`
   - File `.bin` ở: `.pio/build/esp32cam/firmware.bin`
   - ThingsBoard → OTA Updates → Upload

2. **Set shared attributes**:
   ```json
   {
     "fw_version": "1.0.1",
     "fw_url": "https://your-server.com/firmware.bin"
   }
   ```

3. **ESP32 tự động**:
   - Nhận attributes
   - So sánh version
   - Download firmware mới
   - Flash và restart

### Cách 2: Manual Upload

```bash
# Build firmware
pio run

# Upload qua serial
pio run -t upload
```

## Xử Lý Sự Cố

### Camera init failed

**Triệu chứng**: Serial hiện "Camera init failed: 0x105"

**Giải pháp**:
1. Kiểm tra kết nối camera ribbon cable
2. Dùng nguồn 5V 2A (không dùng USB)
3. Thêm tụ 100µF trên đường 5V
4. Thử frame size khác:
   ```cpp
   #define CAMERA_FRAME_SIZE FRAMESIZE_SVGA
   ```

### WiFi không kết nối

**Triệu chứng**: Stuck ở "Connecting to WiFi..."

**Giải pháp**:
1. Reset WiFi settings (uncomment trong code):
   ```cpp
   wm.resetSettings(); // Thêm trước wm.autoConnect()
   ```
2. Xóa flash:
   ```bash
   pio run -t erase
   pio run -t upload
   ```

### MQTT disconnect liên tục

**Triệu chứng**: MQTT ngắt kết nối mỗi vài phút

**Giải pháp**:
1. Kiểm tra WiFi signal
2. Tăng keepalive trong `config.h`:
   ```cpp
   #define MQTT_KEEPALIVE 60
   ```
3. Kiểm tra ThingsBoard server status

### Upload ảnh thất bại

**Triệu chứng**: HTTP POST trả về 5xx error

**Giải pháp**:
1. Verify `BACKEND_URL` đúng
2. Kiểm tra VPS firewall cho phép port 8000
3. Tăng timeout trong `config.h`:
   ```cpp
   #define HTTP_TIMEOUT_MS 30000  // 30 giây
   ```
4. Giảm chất lượng ảnh:
   ```cpp
   #define CAMERA_JPEG_QUALITY 15
   ```

### Memory leak / crash

**Triệu chứng**: ESP32 restart sau 5-10 lần upload

**Giải pháp**:
- Verify có gọi `camera_release(fb)` sau mỗi lần chụp
- Verify có gọi `free(buffer)` sau HTTP post
- Xem serial monitor có "Guru Meditation Error" không

### Provisioning thất bại

**Triệu chứng**: "Provision failed: 404"

**Giải pháp**:
1. Verify ThingsBoard device profile cho phép provisioning
2. Kiểm tra provision keys khớp với ThingsBoard config
3. Verify `HTTP_PROVISION_URL` đúng
4. Xem ThingsBoard logs

## OTA Update Chi Tiết

### Build Firmware

```bash
cd esp32-cam
pio run

# File output: .pio/build/esp32cam/firmware.bin
```

### Upload Lên ThingsBoard

1. ThingsBoard → Dashboards → Settings → OTA Updates
2. Click "Upload firmware"
3. Chọn file `.bin`
4. Nhập version (ví dụ: `1.0.1`)

### Trigger OTA

**Cách 1**: Set shared attributes
```json
{
  "fw_version": "1.0.1",
  "fw_url": "https://your-server.com/firmware.bin"
}
```

**Cách 2**: RPC command (nâng cao)
```json
{
  "method": "ota_update",
  "params": {
    "url": "https://your-server.com/firmware.bin"
  }
}
```

### Theo Dõi OTA

Serial monitor sẽ hiển thị:

```
[OTA] ========================================
[OTA] 🔄 BẮT ĐẦU OTA UPDATE
[OTA] ========================================
[OTA] URL: https://...
[OTA] Firmware size: 1048576 bytes (1024.00 KB)
[OTA] 📥 Đang download firmware...
[OTA] Progress: 10% (104857/1048576 bytes)
[OTA] Progress: 20% (209715/1048576 bytes)
...
[OTA] Progress: 100% (1048576/1048576 bytes)
[OTA] ========================================
[OTA] ✅ UPDATE THÀNH CÔNG!
[OTA] ========================================
[OTA] Đang restart trong 3 giây...
```

## Tiêu Thụ Điện

- Hoạt động (chụp ảnh): ~300mA @ 5V
- Idle (kết nối): ~100mA @ 5V
- Deep sleep: ~10mA @ 5V

Để dùng pin, cần implement deep sleep giữa các lần chụp.

## Cấu Hình Nâng Cao

### Custom Camera Pins

Nếu dùng ESP32-CAM model khác, sửa trong `config.h`:

```cpp
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
// ... các pins khác
```

### Nhiều Camera Cùng Mạng

Mỗi camera cần:
- Device name unique (tự động từ MAC)
- `camera_id` shared attribute khác nhau (1, 2, 3)

## LED Indicator

ESP32-CAM có LED onboard (GPIO 4):

```cpp
#define LED_PIN 4

digitalWrite(LED_PIN, HIGH); // LED sáng
digitalWrite(LED_PIN, LOW);  // LED tắt
```

Dùng để báo trạng thái:
- Nháy nhanh: Đang kết nối
- Sáng liên tục: Đã kết nối
- Nháy chậm: Đang upload
