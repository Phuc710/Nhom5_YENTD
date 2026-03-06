# Database Schema Overview

## 📊 Complete Production Schema

**File**: [`database/schema.sql`](../database/schema.sql)  
**Lines**: 400+  
**Tables**: 10

---

## 🗂️ Tables

### Core Tables

1. **`cameras`** - ESP32-CAM devices
   - Device info (MAC, chip ID, firmware version)
   - Location (lat/lng)
   - Status tracking (active/inactive/maintenance)
   - Last seen timestamp

2. **`violations`** - Main violation records
   - License plate + confidence
   - Image URLs (full + cropped)
   - **Voting metadata** (vote_count, vote_percent, track_id)
   - **Quality metrics** (sharpness, brightness, contrast, noise)
   - Processing time tracking

3. **`ocr_results`** - OCR voting history
   - All OCR results per frame
   - Track ID for object tracking
   - Used for voting analysis

4. **`quality_metrics`** - Image quality per frame
   - Detailed quality scores
   - Frame-by-frame tracking

5. **`detected_plates`** - All detections (including duplicates)
   - Bounding box coordinates
   - For analysis and debugging

### Supporting Tables

6. **`traffic_light_logs`** - Traffic light state history
7. **`esp32_telemetry`** - ESP32 health monitoring
   - Free heap, WiFi RSSI, uptime
   - Upload stats (latency, success rate)

8. **`users`** - Mobile app users
   - License plate as username
   - FCM token for push notifications

9. **`violation_images`** - Multiple images per violation
   - Full, cropped, debug, frame images
   - Quality scores per image

---

## 🔍 Key Features

### Indexes (Performance)
- ✅ `license_plate` - Fast mobile app queries
- ✅ `timestamp DESC` - Dashboard recent violations
- ✅ `camera_id` - Filter by camera
- ✅ `track_id` - Voting analysis

### Triggers (Auto-update)
- ✅ `updated_at` auto-update on cameras/violations/users
- ✅ `last_seen` auto-update when ESP32 sends telemetry

### Views (Common Queries)
- ✅ `violations_with_camera` - Violations + camera details
- ✅ `daily_stats` - Daily violation statistics
- ✅ `camera_health` - ESP32 health monitoring

### Row Level Security (Supabase)
- ✅ Public read for violations
- ✅ Backend-only insert
- ✅ Users see only their own violations

---

## 📋 Sample Queries

### Mobile App: Get violations by plate
```sql
SELECT * FROM violations 
WHERE license_plate = '51F12345' 
ORDER BY timestamp DESC;
```

### Web Dashboard: Recent violations with camera info
```sql
SELECT v.*, c.camera_name, c.location 
FROM violations v 
JOIN cameras c ON v.camera_id = c.camera_id 
ORDER BY v.timestamp DESC 
LIMIT 50;
```

### Debug: OCR voting history
```sql
SELECT frame_id, license_plate, confidence, quality_score 
FROM ocr_results 
WHERE violation_id = 123 
ORDER BY frame_id;
```

### Monitoring: ESP32 health
```sql
SELECT * FROM camera_health;
```

---

## 🚀 Usage

### 1. Create Database
```bash
# Supabase SQL Editor
# Copy & paste schema.sql
```

### 2. Backend Integration
```python
# Already integrated in:
# - backend/services/violation_service.py
# - backend/api/upload.py
```

### 3. Image Storage
```
/uploads/original/cam1_20260202_103045.jpg
/uploads/detected_plates/cam1_20260202_103045_plate.jpg
```

SQL stores **URLs only**, files saved to disk by backend.

---

## 📊 Data Flow

```
ESP32 → Backend → Save images to /uploads
                → Insert violation record with URLs
                → Insert OCR results (voting)
                → Insert quality metrics
                → Insert telemetry

Web/Mobile → Query violations table
          → Get image URLs
          → Display images from /uploads
```

---

**Schema is production-ready** ✅
