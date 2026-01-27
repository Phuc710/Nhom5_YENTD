# OTA Update - Dual Partition System

## Cơ Chế OTA Trên ESP32

ESP32 sử dụng **2 OTA partitions** để cập nhật firmware an toàn:

```
Flash Memory Layout:
┌─────────────────────┐
│  Bootloader         │ ← Không đổi
├─────────────────────┤
│  Partition Table    │ ← Không đổi
├─────────────────────┤
│  NVS (Storage)      │ ← WiFi credentials, token
├─────────────────────┤
│  OTA_0 (app0)       │ ← Firmware hiện tại
├─────────────────────┤
│  OTA_1 (app1)       │ ← Firmware mới download vào đây
├─────────────────────┤
│  SPIFFS/FAT         │ ← File system (optional)
└─────────────────────┘
```

## Quy Trình OTA

### Bước 1: Trạng thái ban đầu
```
Boot Partition: OTA_0
Running: Firmware v1.0.0 (trong OTA_0)
OTA_1: Trống
```

### Bước 2: Nhận OTA update
```
ThingsBoard gửi:
{
  "fw_version": "1.0.1",
  "fw_url": "https://server.com/firmware.bin"
}
```

### Bước 3: Download firmware MỚI vào OTA_1
```
Boot Partition: OTA_0 (vẫn chạy v1.0.0)
Running: v1.0.0 ← VẪN HOẠT ĐỘNG BÌNH THƯỜNG
OTA_1: Đang download v1.0.1... (0% → 100%)
```

**⭐ Quan trọng**: ESP32 **VẪN chụp ảnh, upload** trong khi download!

### Bước 4: Verify firmware
```
- Kiểm tra checksum
- Verify signature (nếu có)
- Đảm bảo firmware hợp lệ
```

### Bước 5: Set boot partition
```
esp_ota_set_boot_partition(ota_1);
```

### Bước 6: Restart
```
ESP.restart();
```

### Bước 7: Boot vào OTA_1
```
Boot Partition: OTA_1 ← MỚI
Running: v1.0.1 (từ OTA_1)
OTA_0: v1.0.0 (cũ, giữ lại để rollback)
```

## Rollback Nếu Lỗi

Nếu firmware mới **không boot được**:

```
1. ESP32 boot vào OTA_1 (v1.0.1)
   ↓
2. Phát hiện lỗi (crash, không kết nối được, etc.)
   ↓
3. Bootloader tự động rollback về OTA_0
   ↓
4. Boot lại vào OTA_0 (v1.0.0 - firmware cũ)
   ↓
5. Hệ thống hoạt động bình thường
```

## Code Implementation

### Partition Table (`partitions.csv`)

```csv
# Name,   Type, SubType, Offset,  Size
nvs,      data, nvs,     0x9000,  0x5000
otadata,  data, ota,     0xe000,  0x2000
app0,     app,  ota_0,   0x10000, 0x1E0000
app1,     app,  ota_1,   0x1F0000,0x1E0000
spiffs,   data, spiffs,  0x3D0000,0x30000
```

### OTA Code (Non-Blocking)

```cpp
// ota.cpp - Non-blocking OTA
void ota_perform_update(const char* firmware_url) {
    if (ota_in_progress) {
        Serial.println("[OTA] ⚠️ OTA đang chạy");
        return;
    }
    
    ota_in_progress = true;
    
    // ⭐ TẠO TASK RIÊNG - KHÔNG BLOCK MAIN LOOP
    xTaskCreate(
        ota_task,           // Task function
        "ota_update",       // Name
        8192,               // Stack size
        (void*)firmware_url,// Parameter
        1,                  // Priority (thấp hơn main)
        NULL                // Task handle
    );
}

void ota_task(void* param) {
    char* url = (char*)param;
    
    Serial.println("[OTA] 🔄 BẮT ĐẦU OTA UPDATE (Background)");
    
    // Get current partition
    const esp_partition_t* running = esp_ota_get_running_partition();
    const esp_partition_t* update_partition = esp_ota_get_next_update_partition(NULL);
    
    Serial.printf("[OTA] Running partition: %s\n", running->label);
    Serial.printf("[OTA] Update partition: %s\n", update_partition->label);
    
    // Download firmware vào partition mới
    esp_ota_handle_t ota_handle;
    esp_ota_begin(update_partition, OTA_SIZE_UNKNOWN, &ota_handle);
    
    // Download từng chunk (KHÔNG BLOCK)
    HTTPClient http;
    http.begin(url);
    WiFiClient* stream = http.getStreamPtr();
    
    uint8_t buff[1024];
    while (http.connected()) {
        size_t available = stream->available();
        if (available) {
            int c = stream->readBytes(buff, min(available, sizeof(buff)));
            esp_ota_write(ota_handle, buff, c);
            
            // ⭐ YIELD để task khác chạy
            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }
    
    // Kết thúc OTA
    esp_ota_end(ota_handle);
    
    // Set boot partition
    esp_ota_set_boot_partition(update_partition);
    
    Serial.println("[OTA] ✅ UPDATE HOÀN TẤT - Restart sau 3s");
    vTaskDelay(pdMS_TO_TICKS(3000));
    
    esp_restart();
    
    vTaskDelete(NULL);
}
```

## Hoạt Động Trong Khi OTA

### Main Loop VẪN Chạy

```cpp
void loop() {
    // ⭐ MQTT vẫn hoạt động
    if (!mqttClient.connected()) {
        mqtt_connect();
    }
    mqttClient.loop();
    
    // ⭐ VẪN chụp ảnh khi đèn đỏ
    if (g_traffic_light_red && !ota_is_in_progress()) {
        // Chỉ tạm dừng chụp khi OTA gần xong (>95%)
        camera_fb_t* fb = camera_capture();
        upload_image(fb, g_camera_id, "red");
        camera_release(fb);
    }
    
    delay(10);
}
```

### Timeline

```
00:00 - Nhận OTA command
00:01 - Tạo OTA task (background)
00:02 - Download 10% | Main loop: Chụp ảnh ✅
00:05 - Download 30% | Main loop: Upload ảnh ✅
00:10 - Download 60% | Main loop: MQTT telemetry ✅
00:15 - Download 90% | Main loop: Vẫn hoạt động ✅
00:18 - Download 100% | Verify firmware
00:19 - Set boot partition
00:20 - Restart
00:23 - Boot vào firmware mới
```

## Rollback Tự Động

### Cơ Chế

ESP32 bootloader có **rollback protection**:

```cpp
// Trong firmware mới, sau khi boot thành công
void setup() {
    // ... khởi tạo ...
    
    // ⭐ ĐÁNH DẤU FIRMWARE HỢP LỆ
    esp_ota_mark_app_valid_cancel_rollback();
    
    Serial.println("[Boot] Firmware mới hoạt động OK!");
}
```

Nếu **KHÔNG** gọi `esp_ota_mark_app_valid_cancel_rollback()`:
- ESP32 sẽ rollback về firmware cũ sau vài lần boot

### Test Rollback

```cpp
// Firmware mới (cố tình lỗi)
void setup() {
    Serial.begin(115200);
    
    // Giả lập lỗi: không kết nối được WiFi
    WiFi.begin("wrong_ssid", "wrong_pass");
    delay(10000);
    
    if (!WiFi.isConnected()) {
        Serial.println("[Error] WiFi failed - KHÔNG mark valid");
        // KHÔNG gọi esp_ota_mark_app_valid_cancel_rollback()
        // → Bootloader sẽ rollback
    }
}
```

## Đồng Bộ Backend/Frontend/ThingsBoard

### 1. Backend Lưu OTA Info

```python
# backend/api/ota.py
@router.post("/api/ota/upload")
async def upload_firmware(file: UploadFile):
    # Lưu firmware
    firmware_path = f"uploads/firmware/{file.filename}"
    with open(firmware_path, "wb") as f:
        f.write(await file.read())
    
    # Lưu vào database
    firmware_record = {
        "version": "1.0.1",
        "filename": file.filename,
        "url": f"https://your-server.com/uploads/firmware/{file.filename}",
        "uploaded_at": datetime.now()
    }
    
    supabase.table("firmware_versions").insert(firmware_record).execute()
    
    return {"success": True, "url": firmware_record["url"]}
```

### 2. Frontend Trigger OTA

```javascript
// frontend/js/ota.js
async function triggerOTA(deviceId, firmwareUrl, version) {
    // Gọi API để set ThingsBoard attributes
    const response = await fetch('/api/thingsboard/set-attributes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            device_id: deviceId,
            attributes: {
                fw_version: version,
                fw_url: firmwareUrl
            }
        })
    });
    
    alert('OTA update đã được trigger!');
}
```

### 3. ThingsBoard Nhận & Gửi Về ESP32

```
Backend → ThingsBoard API:
POST /api/plugins/telemetry/DEVICE/DEVICE_ID/attributes/SHARED_SCOPE

Body:
{
  "fw_version": "1.0.1",
  "fw_url": "https://..."
}

↓

ThingsBoard → ESP32 (MQTT):
Topic: v1/devices/me/attributes
Payload: {"fw_version":"1.0.1","fw_url":"https://..."}

↓

ESP32 nhận → Bắt đầu OTA
```

## Monitoring OTA Progress

### ESP32 Publish Progress

```cpp
void ota_task(void* param) {
    // ...
    
    while (downloading) {
        // Download chunk
        
        // Publish progress
        int progress = (downloaded * 100) / total;
        char telemetry[128];
        sprintf(telemetry, "{\"ota_progress\":%d}", progress);
        mqttClient.publish("v1/devices/me/telemetry", telemetry);
        
        vTaskDelay(pdMS_TO_TICKS(1000)); // Mỗi giây
    }
}
```

### Frontend Hiển Thị Progress

```javascript
// Realtime progress từ ThingsBoard
const ws = new WebSocket('wss://tcm-iot.imespro.ai/api/ws');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.ota_progress) {
        updateProgressBar(data.ota_progress);
    }
};
```

## Best Practices

### 1. Firmware Versioning

```cpp
// platformio.ini
[env:esp32cam]
build_flags = 
    -D VERSION=\"1.0.1\"
    -D BUILD_DATE=\"2026-01-27\"
```

### 2. Checksum Verification

```cpp
// Verify MD5 checksum
if (Update.end()) {
    String md5 = Update.md5String();
    if (md5 == expected_md5) {
        Serial.println("[OTA] ✅ Checksum OK");
    } else {
        Serial.println("[OTA] ❌ Checksum FAILED");
        Update.abort();
    }
}
```

### 3. Staged Rollout

```
1. Upload firmware lên server
2. Test trên 1 device
3. Nếu OK → deploy 10% devices
4. Monitor 24h
5. Nếu stable → deploy 100%
```

## Tóm Tắt

✅ **2 OTA partitions**: ota_0 (hiện tại) + ota_1 (mới)
✅ **Non-blocking**: Download background, main loop vẫn chạy
✅ **Auto rollback**: Nếu firmware mới lỗi
✅ **Đồng bộ**: Backend ↔ ThingsBoard ↔ ESP32
✅ **Progress tracking**: Real-time qua MQTT
