# Evidence API Reference

> Base URL: `http://your-server:8000`
> Tất cả ảnh trả về **WebP** — nhẹ hơn JPEG 30-35%, mobile friendly.

---

## Thiết kế: 3 loại ảnh bằng chứng

| Loại | Key | Mô tả |
|------|-----|-------|
| **Original** | `images.original` | Ảnh gốc, **KHÔNG có overlay** — bằng chứng pháp lý |
| **Vehicle** | `images.vehicle` | Crop xe + **khung đỏ + tên biển số** |
| **Plate** | `images.plate` | Crop biển số **phóng to + viền vàng + text bên dưới** |

```
┌─────────────────────────────────────────────────┐
│  ORIGINAL (full frame, no overlay)              │
│                                                 │
│  ┌──────────────────┐                           │
│  │ MP04CF0655  95%  │  ← vehicle crop + red box │
│  │                  │                           │
│  │   [Car image]    │                           │
│  └──────────────────┘                           │
│                                                 │
│  ┌──────────────────┐                           │
│  │  [Plate image]   │  ← plate crop + yellow    │
│  │  MP04CF0655      │    border + text below    │
│  └──────────────────┘                           │
└─────────────────────────────────────────────────┘
```

---

## Endpoints

### 1. List violations (feed with thumbnails)

```
GET /evidence/violations
```

**Query params:**

| Param | Type | Default | Mô tả |
|-------|------|---------|-------|
| `camera_id` | int | – | Lọc theo camera |
| `license_plate` | string | – | Tìm kiếm biển số (partial) |
| `violation_type` | string | – | `red_light`, `speeding`, ... |
| `limit` | int | 20 | Mobile: 20, Web: 50 |
| `offset` | int | 0 | Pagination |

**Response:**
```json
{
  "items": [
    {
      "id": 42,
      "timestamp": "2026-04-08T14:30:00Z",
      "timestamp_vn": "2026-04-08 21:30:00",
      "violation_type": "red_light",
      "traffic_light_state": "red",
      "license_plate": "MP04CF0655",
      "confidence": 0.95,
      "thumbnail_url": "https://xxx.supabase.co/storage/v1/object/public/violations/cam1/...vehicle.webp",
      "camera_id": 1,
      "camera_name": "Cam Ngã Tư 1",
      "camera_location": "Ngã tư Hồ Chí Minh"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

---

### 2. Get violation evidence (full detail + all images)

```
GET /evidence/violations/{violation_id}
```

**Response:**
```json
{
  "id": 42,
  "timestamp": "2026-04-08T14:30:00Z",
  "timestamp_vn": "2026-04-08 21:30:00",
  "violation_type": "red_light",
  "traffic_light_state": "red",

  "camera": {
    "id": 1,
    "name": "Cam Ngã Tư 1",
    "location": "Ngã tư Hồ Chí Minh"
  },

  "vehicle": {
    "type": "car",
    "track_id": 7,
    "bbox": { "x1": 120, "y1": 80, "x2": 480, "y2": 360, "width": 360, "height": 280 }
  },

  "plate": {
    "text": "MP04CF0655",
    "confidence": 0.95,
    "vote_count": 12,
    "vote_percent": 91.7
  },

  "images": {
    "original": {
      "url": "https://xxx.supabase.co/.../cam1/..._original.webp",
      "format": "webp"
    },
    "vehicle": {
      "url": "https://xxx.supabase.co/.../cam1/..._vehicle.webp",
      "format": "webp"
    },
    "plate": {
      "url": "https://xxx.supabase.co/.../cam1/..._plate.webp",
      "format": "webp"
    }
  },

  "processing_time_ms": 45
}
```

---

### 3. Serve image directly (local storage fallback)

```
GET /evidence/violations/{violation_id}/image/{image_type}
```

`image_type`: `original` | `vehicle` | `plate`

- Nếu Supabase → **302 redirect** về CDN URL
- Nếu local → serve binary **image/webp** trực tiếp

---

### 4. Live snapshot (no violation needed)

```
GET /evidence/snapshot/{camera_id}?quality=80
```

Returns current stream frame as WebP. Dùng cho live preview.

---

### 5. Stats summary

```
GET /evidence/stats
```

```json
{
  "total_violations": 1520,
  "today": { "date": "2026-04-08", "count": 47 },
  "cameras": [
    { "id": 1, "name": "Cam 1", "total_violations": 800, "status": "active" }
  ],
  "daily_trend": [
    { "date": "2026-04-08", "count": 47 },
    { "date": "2026-04-07", "count": 52 }
  ]
}
```

---

## Submit violation + upload images

### Từ internal pipeline (nhanh nhất — base64 JSON)

```
POST /violations/with-images/b64
Content-Type: application/json

{
  "camera_id": 1,
  "timestamp": "2026-04-08T14:30:00Z",
  "violation_type": "red_light",
  "traffic_light_state": "red",
  "license_plate": "MP04CF0655",
  "confidence": 0.95,
  "track_id": 7,
  "full_frame_b64": "<base64_string>",
  "vehicle_bbox": [120, 80, 480, 360],
  "plate_bbox": [160, 300, 380, 350],
  "vote_count": 12,
  "vote_percent": 91.7
}
```

**Response:**
```json
{
  "violation_id": 42,
  "message": "Violation recorded.",
  "images": {
    "original": { "url": "https://..." },
    "vehicle":  { "url": "https://..." },
    "plate":    { "url": "https://..." }
  }
}
```

### Từ app/mobile (multipart form)

```
POST /violations/with-images
Content-Type: multipart/form-data

camera_id=1
timestamp=2026-04-08T14:30:00Z
license_plate=MP04CF0655
vehicle_x1=120&vehicle_y1=80&vehicle_x2=480&vehicle_y2=360
plate_x1=160&plate_y1=300&plate_x2=380&plate_y2=350
full_frame=<file upload>
```

---

## Integration guide

### Web (JavaScript)

```js
// Feed
const res = await fetch('/evidence/violations?limit=20');
const { items } = await res.json();
items.forEach(v => {
  // thumbnail_url có bbox overlay — xài để hiển thị card
  img.src = v.thumbnail_url;
});

// Detail
const detail = await fetch(`/evidence/violations/${id}`).then(r => r.json());
originalImg.src = detail.images.original.url;  // pháp lý
vehicleImg.src  = detail.images.vehicle.url;   // hiển thị
plateImg.src    = detail.images.plate.url;     // biển số
plateText.textContent = detail.plate.text;     // MP04CF0655
```

### Mobile (React Native / Flutter)

```js
// Flutter
final res = await http.get(Uri.parse('$base/evidence/violations/$id'));
final data = ViolationEvidence.fromJson(jsonDecode(res.body));

// Hiển thị biển số lớn ở đầu
Text(data.plate.text ?? '---')

// 3 ảnh
Image.network(data.images.original.url)   // bằng chứng gốc
Image.network(data.images.vehicle.url)    // xe có bbox
Image.network(data.images.plate.url)      // biển số zoom
```

### Python (internal)

```python
import httpx

# Submit từ pipeline
resp = httpx.post('http://localhost:8000/violations/with-images/b64', json={
    "camera_id": 1,
    "timestamp": "2026-04-08T14:30:00Z",
    "full_frame_b64": base64_encode(frame),
    "vehicle_bbox": [x1, y1, x2, y2],
    "plate_bbox": [px1, py1, px2, py2],
    "license_plate": "MP04CF0655",
    "confidence": 0.95,
})
data = resp.json()
print(data["images"]["plate"]["url"])  # plate image URL
```
