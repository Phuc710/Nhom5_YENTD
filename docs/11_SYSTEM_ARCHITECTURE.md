# System Architecture

## 🏗️ Components

```
┌──────────────┐   MQTT    ┌─────────────┐
│  ESP32-CAM   ├──────────►│ ThingsBoard │
│  (Hardware)  │           │ (IoT MQTT)  │
└──────┬───────┘           └─────────────┘
       │ HTTP
       ↓ /api/upload
┌──────────────┐           ┌─────────────┐
│   Backend    ├──────────►│  Supabase   │
│   FastAPI    │  PostgreSQL  (Database)  │
└──────┬───────┘           └─────────────┘
       │
       ↓ HTTP
┌──────────────┬─────────────┐
│ Web Dashboard│ Mobile App  │
│   (Admin)    │   (User)    │
└──────────────┴─────────────┘
```

---

## 📊 Data Flow

```
① ESP32 Traffic Light → MQTT publish "red_light"
② ESP32-CAM subscribe → Capture 5 frames (1 FPS)
③ Upload HTTP → Backend /api/upload
④ Backend:
   ├─ Quality score
   ├─ YOLO detect
   ├─ Track (SORT)
   ├─ OCR
   ├─ Vote per vehicle
   └─ Save to DB
⑤ Response → ESP32
⑥ Users query → Web/Mobile
```

---

## ⚙️ ESP32-CAM

**Config**: Zero-touch provisioning via ThingsBoard  
**Capture**: 5 frames @ 1 FPS, JPEG quality 12  
**Upload**: HTTP POST multipart/form-data  
**Size**: ~180KB/image → 900KB total

---

## 🔧 Backend (FastAPI)

```python
# Main routes
POST   /api/upload           # ESP32 upload images
GET    /api/violations       # List all
GET    /api/violations/{id}  # Detail
GET    /api/violations/by-plate/{plate}  # Mobile query
GET    /api/cameras          # Camera list
GET    /api/stats            # Dashboard stats
```

**Processing**:
- Quality scoring: OpenCV
- Detection: YOLOv5 (GPU)
- OCR: PaddleOCR
- Tracking: SORT

---

## 💾 Database (Supabase PostgreSQL)

**Tables**: cameras, violations, ocr_results, users  
**Indexes**: plate, camera_id, timestamp  
**RLS**: Enabled per table

---

## 📱 Web Dashboard (PHP)

```
/index.php           # Stats, charts
/violations.php      # List + filters
/violation_detail.php # Full detail
/cameras.php         # Management
```

---

## 📲 Mobile App (Android Kotlin)

```
LoginScreen     # Input plate
ListScreen      # Show violations
DetailScreen    # Images, map, metadata
```

---

**Tech Stack**:
- ESP32: Arduino + PlatformIO
- Backend: Python FastAPI + PyTorch
- Database: PostgreSQL (Supabase)
- Web: PHP + JavaScript
- Mobile: Kotlin + Jetpack Compose
