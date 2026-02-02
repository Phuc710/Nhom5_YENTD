# System Architecture - Complete Overview

## 🎯 Tổng Quan Hệ Thống

Hệ thống phát hiện vi phạm giao thông hoàn toàn tự động sử dụng:
- **ESP32-CAM**: Chụp ảnh đa khung hình (multi-shot)
- **YOLO AI + OCR**: Phát hiện và đọc biển số
- **Object Tracking + Voting**: Tăng độ chính xác
- **ThingsBoard IoT**: Quản lý thiết bị
- **Backend API**: Xử lý ảnh và lưu trữ
- **Web + Mobile**: Tra cứu vi phạm

---

## 📐 Kiến Trúc Tổng Thể

```
┌────────────────────────────────────────────────────────────────────┐
│                         HARDWARE LAYER                              │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐           ┌──────────────────┐              │
│  │  ESP32-CAM #1    │           │ ESP32-CAM #2     │              │
│  │  (Gò Vấp)        │           │ (Củ Chi)         │  ... #N      │
│  │  - Camera OV2640 │           │  - Camera OV2640 │              │
│  │  - WiFi          │           │  - WiFi          │              │
│  │  - MQTT Client   │           │  - MQTT Client   │              │
│  └────────┬─────────┘           └────────┬─────────┘              │
│           │                              │                         │
│  ┌────────▼─────────┐           ┌────────▼─────────┐              │
│  │ ESP32 Traffic    │           │ ESP32 Traffic    │              │
│  │ Light #1         │           │ Light #2         │  ... #N      │
│  │ - LED: R/Y/G     │           │ - LED: R/Y/G     │              │
│  │ - MQTT Publish   │           │ - MQTT Publish   │              │
│  └──────────────────┘           └──────────────────┘              │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ MQTT (port 1883)
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│                         IOT PLATFORM LAYER                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │            ThingsBoard IoT Platform                           │ │
│  │  tcm-iot.imespro.ai (103.249.117.212:1883)                   │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │  - Device Provisioning (Zero-Touch)                          │ │
│  │  - Shared Attributes (camera_id, location, upload_url, ...)  │ │
│  │  - Client Attributes (mac, chip_id, model)                   │ │
│  │  - Telemetry (wifi_rssi, free_heap, upload_ok)              │ │
│  │  - OTA Firmware Update                                        │ │
│  │  - Real-time Monitoring & Alerts                             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ HTTP/HTTPS
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER (VPS)                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                Backend Server (Python FastAPI)                │ │
│  │                Port 8000                                      │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │                                                               │ │
│  │  📡 REST API Endpoints:                                       │ │
│  │    ├─ POST /api/upload (ESP32 upload images)                 │ │
│  │    ├─ GET  /api/violations (list)                            │ │
│  │    ├─ GET  /api/violations/{id} (detail)                     │ │
│  │    ├─ GET  /api/violations/by-plate/{plate} (mobile app)     │ │
│  │    ├─ GET  /api/cameras (list)                               │ │
│  │    ├─ GET  /api/stats (dashboard)                            │ │
│  │    └─ POST /api/login (mobile auth)                          │ │
│  │                                                               │ │
│  │  🤖 AI Processing Pipeline:                                   │ │
│  │    ┌────────────────────────────────────────────────┐        │ │
│  │    │ 1. Multi-Frame Processing (5-7 images)        │        │ │
│  │    │     └─ Quality scoring (sharpness, brightness) │        │ │
│  │    ├────────────────────────────────────────────────┤        │ │
│  │    │ 2. YOLO Detection                              │        │ │
│  │    │     ├─ Vehicle detection (car, truck, bike)    │        │ │
│  │    │     └─ License plate detection                 │        │ │
│  │    ├────────────────────────────────────────────────┤        │ │
│  │    │ 3. Object Tracking (SORT/DeepSORT)             │        │ │
│  │    │     └─ Track same vehicle across frames        │        │ │
│  │    ├────────────────────────────────────────────────┤        │ │
│  │    │ 4. OCR (PaddleOCR / EasyOCR)                   │        │ │
│  │    │     └─ Extract license plate text              │        │ │
│  │    ├────────────────────────────────────────────────┤        │ │
│  │    │ 5. Voting Mechanism                            │        │ │
│  │    │     └─ Vote OCR results per track_id           │        │ │
│  │    ├────────────────────────────────────────────────┤        │ │
│  │    │ 6. Deduplication                               │        │ │
│  │    │     └─ Check duplicate within 5s window        │        │ │
│  │    ├────────────────────────────────────────────────┤        │ │
│  │    │ 7. Save to Database                            │        │ │
│  │    │     └─ violations, ocr_results, quality_metrics│        │ │
│  │    └────────────────────────────────────────────────┘        │ │
│  │                                                               │ │
│  └───────────────────────────────┬───────────────────────────────┘ │
│                                  │                                 │
│                                  │ Database Connection             │
│                                  ▼                                 │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │         Supabase PostgreSQL Database                          │ │
│  │         (your-project.supabase.co)                           │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │  Tables:                                                      │ │
│  │    ├─ cameras                                                │ │
│  │    ├─ violations                                             │ │
│  │    ├─ detected_plates                                        │ │
│  │    ├─ ocr_results (voting)                                   │ │
│  │    ├─ quality_metrics                                        │ │
│  │    ├─ traffic_light_logs                                     │ │
│  │    ├─ users (mobile app)                                     │ │
│  │    └─ violation_images                                       │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              File Storage (uploads/)                          │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │    ├─ uploads/original/          (full images)               │ │
│  │    └─ uploads/detected_plates/   (cropped plates)            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ HTTP/HTTPS API
                   ┌───────────────┴───────────────┐
                   │                               │
                   ▼                               ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│     WEB DASHBOARD            │  │   MOBILE APP (Android)       │
│     (Frontend - PHP/JS)      │  │   (Future: iOS)              │
├──────────────────────────────┤  ├──────────────────────────────┤
│                              │  │                              │
│  📊 Pages:                   │  │  📱 Screens:                 │
│    ├─ Dashboard              │  │    ├─ Login (by plate)      │
│    ├─ Violation List         │  │    ├─ My Violations         │
│    ├─ Violation Detail       │  │    ├─ Violation Detail      │
│    ├─ Camera Management      │  │    └─ Payment (future)      │
│    └─ Statistics             │  │                              │
│                              │  │  🔔 Features:                │
│  🔍 Features:                │  │    ├─ Lookup by plate       │
│    ├─ Real-time update       │  │    ├─ View full+crop images │
│    ├─ Filter by date/camera  │  │    ├─ Location map          │
│    ├─ Search by plate        │  │    └─ Push notifications    │
│    ├─ View images (modal)    │  │                              │
│    └─ Export reports         │  │                              │
│                              │  │                              │
└──────────────────────────────┘  └──────────────────────────────┘
```

---

## 🔄 Data Flow: Luồng Hoạt Động Chi Tiết

### Scenario: Xe Vượt Đèn Đỏ

```
① Đèn Giao Thông Chuyển ĐỎ
   ├─ ESP32 Traffic Light → State machine: GREEN → YELLOW → RED
   ├─ Publish MQTT:
   │    Topic: v1/devices/me/telemetry
   │    Data: {"traffic_light_state": "red", "timestamp": 1674567890}
   └─ ThingsBoard nhận và broadcast

② ESP32-CAM Nhận Signal Đèn Đỏ
   ├─ Subscribe: v1/gateway/+/telemetry (hoặc HTTP polling)
   ├─ Trigger: g_traffic_light_red = true
   └─ Bắt đầu multi-shot capture

③ Multi-Shot Capture (5 ảnh × 1s interval)
   ├─ t=0s: Capture frame #1
   ├─ t=1s: Capture frame #2
   ├─ t=2s: Capture frame #3
   ├─ t=3s: Capture frame #4
   └─ t=4s: Capture frame #5

④ Upload Lên Backend
   ├─ HTTP POST http://VPS_IP:8000/api/upload
   ├─ FormData:
   │    - images[]: 5 files (multipart/form-data)
   │    - camera_id: 1
   │    - timestamp: 2026-02-02T10:00:00Z
   │    - traffic_light_state: "red"
   └─ Timeout: 30s

⑤ Backend Processing
   ├─ Step 1: Save original images
   │    └─ uploads/original/cam1_20260202_100000_frame{0-4}.jpg
   │
   ├─ Step 2: Image Quality Scoring
   │    ┌─ Frame 0: score=72.5 (ok)
   │    ├─ Frame 1: score=88.2 (excellent) ✅
   │    ├─ Frame 2: score=65.1 (mờ)
   │    ├─ Frame 3: score=91.3 (excellent) ✅
   │    └─ Frame 4: score=45.8 (reject - too dark)
   │
   ├─ Step 3: YOLO Detection (chỉ frames score >= 70)
   │    ┌─ Frame 1:
   │    │    ├─ Vehicle #1: bbox=[100, 200, 400, 500], class=car
   │    │    └─ Plate #1: bbox=[150, 350, 250, 380]
   │    └─ Frame 3:
   │         ├─ Vehicle #1: bbox=[120, 210, 420, 510]  (same car)
   │         ├─ Vehicle #2: bbox=[500, 100, 700, 300]  (new car)
   │         └─ Plate #1: bbox=[160, 360, 260, 390]
   │         └─ Plate #2: bbox=[550, 180, 640, 210]
   │
   ├─ Step 4: Object Tracking (SORT/DeepSORT)
   │    ├─ Track ID #1: Vehicle #1 (frame 1, 3)
   │    └─ Track ID #2: Vehicle #2 (frame 3)
   │
   ├─ Step 5: OCR per Plate
   │    ┌─ Track #1:
   │    │    ├─ Frame 1: "51F12345" (conf=0.92)
   │    │    └─ Frame 3: "51F12345" (conf=0.88)
   │    └─ Track #2:
   │         └─ Frame 3: "29B98765" (conf=0.85)
   │
   ├─ Step 6: Voting Per Track
   │    ├─ Track #1: "51F12345" (vote=2/2 = 100%) ✅
   │    └─ Track #2: "29B98765" (vote=1/1 = 100%) ✅
   │
   ├─ Step 7: Deduplication Check
   │    ├─ Query: violations WHERE camera_id=1 
   │    │         AND license_plate='51F12345'
   │    │         AND timestamp > (now - 5s)
   │    ├─ Result: None (không trùng)
   │    └─ Proceed to create record
   │
   └─ Step 8: Save to Database
        ├─ violations table:
        │    ├─ camera_id: 1
        │    ├─ license_plate: "51F12345"
        │    ├─ confidence: 0.90
        │    ├─ full_image_url: "/uploads/original/cam1_...jpg"
        │    ├─ cropped_plate_url: "/uploads/detected_plates/plate_...jpg"
        │    ├─ timestamp: 2026-02-02T10:00:03Z
        │    ├─ vote_count: 2
        │    ├─ vote_percent: 100.0
        │    └─ image_quality_score: 89.8
        │
        ├─ ocr_results table (for analysis):
        │    ├─ Record #1: frame=1, plate="51F12345", conf=0.92
        │    └─ Record #2: frame=3, plate="51F12345", conf=0.88
        │
        └─ quality_metrics table:
             ├─ Frame 0: overall=72.5, sharpness=85, brightness=142
             ├─ Frame 1: overall=88.2, sharpness=120, brightness=135
             └─ ...

⑥ Response to ESP32
   ├─ HTTP 200 OK
   └─ JSON: {
         "success": true,
         "violations_created": 2,
         "violations": [
             {"id": 123, "license_plate": "51F12345"},
             {"id": 124, "license_plate": "29B98765"}
         ]
     }

⑦ ESP32 Publish Telemetry
   ├─ MQTT: v1/devices/me/telemetry
   └─ Data: {
         "upload_ok": true,
         "http_code": 200,
         "latency_ms": 3450,
         "violations_count": 2
     }

⑧ User Tra Cứu (Web hoặc Mobile)
   ├─ Web: GET /api/violations?camera_id=1&date=2026-02-02
   ├─ Mobile: GET /api/violations/by-plate/51F12345
   └─ Response: Danh sách vi phạm + ảnh
```

---

## 🔑 Key Components Breakdown

### ESP32-CAM Firmware

**Tech Stack**:
- Platform: ESP32 AI-Thinker
- Camera: OV2640 (2MP)
- Framework: Arduino + PlatformIO
- Libraries: WiFiManager, PubSubClient (MQTT), HTTPClient

**Core Modules**:
```cpp
include/
  ├─ config.h           // ONLY provision_key hardcoded
  ├─ camera.h           // Camera init & capture
  ├─ network.h          // WiFi + MQTT + HTTP
  ├─ upload.h           // Multi-frame upload
  └─ ota.h              // OTA firmware update

src/
  └─ main.cpp           // Main loop
```

**Memory Management**:
- PSRAM: 4MB (for frame buffers)
- Heap: ~200KB free (ESP32 4MB flash)
- MQTT buffer: 2KB
- HTTP buffer: 16KB (chunked upload)

---

### Backend API (Python FastAPI)

**Tech Stack**:
- Framework: FastAPI
- ASGI: Uvicorn (4 workers)
- AI: YOLOv5, PaddleOCR
- Image: OpenCV, NumPy
- Tracking: SORT / DeepSORT
- DB: Supabase (PostgreSQL)

**Project Structure**:
```
backend/
├─ main.py                  # FastAPI app entry
├─ api/
│  ├─ upload.py             # Image upload & processing
│  ├─ violations.py         # CRUD violations
│  ├─ cameras.py            # Camera management
│  └─ stats.py              # Statistics
├─ ml/
│  ├─ detector.py           # YOLO wrapper
│  ├─ ocr.py                # OCR wrapper
│  ├─ tracker.py            # Object tracking
│  └─ quality_scorer.py     # Image quality metrics
├─ services/
│  ├─ image_service.py      # Image processing pipeline
│  ├─ violation_service.py  # Business logic
│  └─ voting_service.py     # Voting mechanism
├─ database/
│  ├─ models.py             # Pydantic models
│  └─ supabase_client.py    # DB connection
└─ utils/
   └─ deduplication.py      # Duplicate check
```

---

## 📊 Performance Metrics

### ESP32-CAM

| Metric | Value |
|--------|-------|
| Capture interval | 1s (1 FPS) |
| Image size (UXGA) | ~180KB (JPEG quality=12) |
| Upload time (WiFi) | 2-4s per image |
| Free heap after upload | ~150KB |
| MQTT latency | <100ms |
| OTA update time | ~60s (for 1MB firmware) |

### Backend Processing

| Metric | Value |
|--------|-------|
| YOLO inference (CPU) | ~500ms per image |
| YOLO inference (GPU) | ~50ms per image |
| OCR (PaddleOCR CPU) | ~300ms per plate |
| Tracking overhead | ~10ms per frame |
| Total pipeline (5 frames) | ~5-10s |
| Concurrent requests | 4 workers (Uvicorn) |

### Database

| Metric | Value |
|--------|-------|
| Read latency | <50ms (Supabase) |
| Write latency | <100ms |
| Query `violations` | <200ms (with index) |
| Storage | ~500KB per violation (2 images) |

---

## 🛡️ Security & Reliability

### Current (Demo)

- ⚠️ HTTP (no encryption)
- ⚠️ No authentication on API
- ⚠️ Provision keys in code
- ⚠️ No rate limiting

### Production Recommendations

1. **HTTPS Everywhere**
   ```nginx
   server {
       listen 443 ssl;
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
   }
   ```

2. **API Authentication**
   - JWT tokens for web/mobile
   - API keys for ESP32
   - Rate limiting (100 req/min)

3. **Database Security**
   - Supabase RLS (Row Level Security)
   - Connection pooling
   - Encrypted backups

4. **Device Security**
   - VPN for ESP32 (WireGuard)
   - Encrypted WiFi (WPA3)
   - Provision keys in secure storage

---

## ✅ Deployment Checklist

- [ ] VPS Server (2GB RAM, 2 vCPU minimum)
- [ ] Supabase project created
- [ ] ThingsBoard server running
- [ ] Domain & SSL certificate
- [ ] ESP32 devices flashed with firmware
- [ ] Web dashboard deployed
- [ ] Mobile app published (APK)
- [ ] Monitoring setup (Prometheus/Grafana)
- [ ] Backup automation

---

**Tổng Kết**: Hệ thống hoàn chỉnh với architecture chuẩn production, hỗ trợ multi-shot capture, advanced image processing, object tracking, và voting mechanism để đảm bảo độ chính xác cao nhất.
