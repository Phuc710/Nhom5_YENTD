# Web Dashboard - UI/UX Features & Design

## 🎯 Mục Đích

Web dashboard cho admin để:
- Xem tất cả vi phạm real-time
- Quản lý cameras
- Tra cứu theo biển số, thời gian, địa điểm
- Xem ảnh vi phạm (full + cropped)
- Thống kê & báo cáo

---

## 📐 Trang Structure

```
/
├─ index.php                # Dashboard chính
├─ violations.php           # Danh sách vi phạm
├─ violation_detail.php     # Chi tiết 1 vi phạm
├─ cameras.php              # Quản lý cameras
├─ statistics.php           # Thống kê
├─ search.php               # Tìm kiếm nâng cao
└─ login.php                # Admin login (optional)
```

---

## 🏠 Page 1: Dashboard Chính (`index.php`)

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  HEADER                                                  │
│  🚦 TRAFFIC VIOLATION DETECTION SYSTEM                   │
│  Admin: Nguyen Van A | Logout                           │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  STATISTICS CARDS                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │  TOTAL   │ │  TODAY   │ │  7 DAYS  │ │ 30 DAYS  │  │
│  │  1,234   │ │   45     │ │   312    │ │   890    │  │
│  │ violations│ │violations│ │violations│ │violations│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  CHARTS                                                  │
│  ┌────────────────────────┐ ┌──────────────────────┐   │
│  │ Violations by Hour     │ │ Top Locations        │   │
│  │ (Line Chart)           │ │ (Bar Chart)          │   │
│  └────────────────────────┘ └──────────────────────┘   │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  RECENT VIOLATIONS (Last 10)                            │
│  ┌───────────────────────────────────────────────────┐ │
│  │ #123 | 51F-12345 | Gò Vấp | 2026-02-02 10:15:30  │ │
│  │ [Image] [View Detail]                             │ │
│  ├───────────────────────────────────────────────────┤ │
│  │ #122 | 29B-98765 | Củ Chi | 2026-02-02 09:45:12  │ │
│  │ [Image] [View Detail]                             │ │
│  └───────────────────────────────────────────────────┘ │
│  [View All Violations]                                  │
└─────────────────────────────────────────────────────────┘
```

### API Calls

```javascript
// Fetch statistics
fetch('/api/stats')
  .then(res => res.json())
  .then(data => {
    document.getElementById('total').textContent = data.total;
    document.getElementById('today').textContent = data.today;
    // ...
  });

// Fetch recent violations
fetch('/api/violations?limit=10&sort=timestamp:desc')
  .then(res => res.json())
  .then(data => {
    renderViolations(data.violations);
  });

// Auto-refresh mỗi 30s
setInterval(() => {
  fetchUpdates();
}, 30000);
```

---

## 📝 Page 2: Danh Sách Vi Phạm (`violations.php`)

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  FILTERS                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Camera   │ │   Date   │ │  Plate   │ │  Search  │  │
│  │  [All ▼] │ │[DatePick]│ │ [Input]  │ │ [Button] │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  VIOLATIONS TABLE                                        │
│  ┏━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓  │
│  ┃ ID ┃   Plate   ┃  Location  ┃    Timestamp     ┃  │
│  ┣━━━━╋━━━━━━━━━━━╋━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━┫  │
│  ┃123 ┃ 51F-12345 ┃  Gò Vấp    ┃ 02/02 10:15:30   ┃  │
│  ┃    ┃ [Image]   ┃            ┃ [View] [Delete]  ┃  │
│  ┣━━━━╋━━━━━━━━━━━╋━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━┫  │
│  ┃122 ┃ 29B-98765 ┃  Củ Chi    ┃ 02/02 09:45:12   ┃  │
│  ┃    ┃ [Image]   ┃            ┃ [View] [Delete]  ┃  │
│  ┗━━━━┻━━━━━━━━━━━┻━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━┛  │
│                                                          │
│  [◄ Prev]  Page 1 of 25  [Next ►]                      │
└─────────────────────────────────────────────────────────┘
```

### Features

1. **Filters**:
   - Camera dropdown (All, Gò Vấp, Củ Chi, ...)
   - Date range picker
   - License plate search
   - Confidence threshold slider

2. **Table**:
   - Sortable columns (click header)
   - Thumbnail preview
   - Quick actions (View, Delete)
   - Pagination (20 items/page)

3. **Bulk Actions**:
   - Select multiple
   - Delete selected
   - Export to CSV/PDF

### API Call

```javascript
const filters = {
  camera_id: document.getElementById('cameraFilter').value,
  date_from: document.getElementById('dateFrom').value,
  date_to: document.getElementById('dateTo').value,
  license_plate: document.getElementById('plateSearch').value,
  page: 1,
  limit: 20
};

const query = new URLSearchParams(filters).toString();

fetch(`/api/violations?${query}`)
  .then(res => res.json())
  .then(data => {
    renderTable(data.violations);
    renderPagination(data.total, data.page, data.limit);
  });
```

---

## 🔍 Page 3: Chi Tiết Vi Phạm (`violation_detail.php?id=123`)

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  VIOLATION #123                                          │
│  [◄ Back to List]                     [Delete]          │
└─────────────────────────────────────────────────────────┘
┌──────────────────────────┬──────────────────────────────┐
│  FULL IMAGE              │  CROPPED PLATE               │
│  ┌──────────────────────┐│  ┌─────────────────────┐    │
│  │                      ││  │                     │    │
│  │  [Ảnh xe đầy đủ]    ││  │  [Ảnh biển số crop] │    │
│  │                      ││  │                     │    │
│  │   1600 x 1200       ││  │    300 x 100        │    │
│  └──────────────────────┘│  └─────────────────────┘    │
│  [🔍 View Full Size]     │  [🔍 View Full Size]        │
└──────────────────────────┴──────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  VIOLATION DETAILS                                       │
│  ┌────────────────────────────────────────────────────┐ │
│  │ License Plate:     51F-12345                       │ │
│  │ Confidence:        92.5% ⭐⭐⭐⭐⭐                  │ │
│  │ Vote Count:        3/5 (60%)                       │ │
│  │ Quality Score:     88.2/100 ⭐⭐⭐⭐               │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Camera:            Camera Gò Vấp (#1)              │ │
│  │ Location:          Ngã tư Gò Vấp                   │ │
│  │ Coordinates:       10.8231, 106.6297 [Map 🗺️]     │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Timestamp:         2026-02-02 10:15:30 +07:00      │ │
│  │ Traffic Light:     🔴 RED                          │ │
│  │ Violation Type:    Red Light Violation             │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Image Quality Metrics:                             │ │
│  │   - Sharpness:     120.5                           │ │
│  │   - Brightness:    135.2                           │ │
│  │   - Contrast:      58.7                            │ │
│  │   - Noise Level:   12.3                            │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  OCR VOTING HISTORY (Debug)                             │
│  ┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┓  │
│  ┃ Frame  ┃   Plate     ┃ Confidence ┃  Quality   ┃  │
│  ┣━━━━━━━━╋━━━━━━━━━━━━━╋━━━━━━━━━━━━╋━━━━━━━━━━━━┫  │
│  ┃   0    ┃ 51F-12345 ✅┃   0.85     ┃    72.5    ┃  │
│  ┃   1    ┃ 51F-12345 ✅┃   0.92     ┃    88.2    ┃  │
│  ┃   2    ┃ 51F-1234S ❌┃   0.78     ┃    65.1    ┃  │
│  ┃   3    ┃ 51F-12345 ✅┃   0.88     ┃    91.3    ┃  │
│  ┃   4    ┃ None ❌     ┃   0.00     ┃    45.8    ┃  │
│  ┗━━━━━━━━┻━━━━━━━━━━━━━┻━━━━━━━━━━━━┻━━━━━━━━━━━━┛  │
│  Winner: 51F-12345 (3/5 votes = 60%)                    │
└─────────────────────────────────────────────────────────┘
```

### Features

1. **Image Viewer**:
   - Modal full-screen view
   - Zoom in/out
   - Download image

2. **Map Integration**:
   - Leaflet.js or Google Maps
   - Show camera location
   - Street view (if available)

3. **Metadata**:
   - Complete violation info
   - Voting history
   - Quality metrics

### API Call

```javascript
fetch(`/api/violations/${violationId}`)
  .then(res => res.json())
  .then(data => {
    document.getElementById('plate').textContent = data.license_plate;
    document.getElementById('confidence').textContent = data.confidence;
    document.getElementById('fullImage').src = data.full_image_url;
    document.getElementById('croppedImage').src = data.cropped_plate_url;
    // ...
    
    // Fetch OCR results
    fetch(`/api/violations/${violationId}/ocr-results`)
      .then(res => res.json())
      .then(ocrData => {
        renderOCRTable(ocrData.results);
      });
  });
```

---

## 📷 Page 4: Quản Lý Cameras (`cameras.php`)

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  CAMERAS MANAGEMENT                                      │
│  [+ Add New Camera]                                      │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  CAMERAS LIST                                            │
│  ┏━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓  │
│  ┃  ID  ┃    Name     ┃    Location    ┃  Status  ┃  │
│  ┣━━━━━━╋━━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━╋━━━━━━━━━━┫  │
│  ┃  1   ┃ Gò Vấp      ┃ Ngã tư GV      ┃ 🟢 Active┃  │
│  ┃      ┃ MAC: AA:BB..┃ (10.82, 106.6) ┃ [Edit]   ┃  │
│  ┣━━━━━━╋━━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━╋━━━━━━━━━━┫  │
│  ┃  2   ┃ Củ Chi      ┃ Ngã tư 22/12   ┃ 🔴 Offline┃│
│  ┃      ┃ MAC: CC:DD..┃ (10.97, 106.4) ┃ [Edit]   ┃  │
│  ┗━━━━━━┻━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━┻━━━━━━━━━━┛  │
└─────────────────────────────────────────────────────────┘
```

### Features

1. **Add/Edit Camera**:
   - Camera ID
   - Name
   - Location (text + lat/lng picker)
   - Status (active/inactive/maintenance)
   
2. **Real-time Status**:
   - Online/Offline indicator
   - Last seen timestamp
   - Telemetry data (WiFi RSSI, free heap)

3. **Statistics Per Camera**:
   - Total violations
   - Avg quality score
   - Uptime

---

## 📊 Page 5: Thống Kê (`statistics.php`)

### Charts

1. **Violations Over Time**
   - Line chart (last 30 days)
   - Group by hour/day/week

2. **Top Violators**
   - Bar chart (license plates with most violations)

3. **Camera Performance**
   - Table: violations per camera
   - Quality score trends

4. **Heatmap**
   - Map with violation density

### Tech Stack

- **Charts**: Chart.js or ApexCharts
- **Maps**: Leaflet.js
- **Export**: jsPDF, html2canvas

---

## 🎨 Design System

### Colors

```css
:root {
  --primary: #2563eb;      /* Blue */
  --success: #10b981;      /* Green */
  --warning: #f59e0b;      /* Yellow */
  --danger: #ef4444;       /* Red */
  --dark: #1f2937;
  --light: #f3f4f6;
}
```

### Typography

```css
body {
  font-family: 'Inter', -apple-system, sans-serif;
  font-size: 16px;
  line-height: 1.6;
}

h1 { font-size: 2rem; font-weight: 700; }
h2 { font-size: 1.5rem; font-weight: 600; }
```

### Components

**Button**:
```html
<button class="btn btn-primary">Primary</button>
<button class="btn btn-danger">Delete</button>
```

**Card**:
```html
<div class="card">
  <div class="card-header">Title</div>
  <div class="card-body">Content</div>
</div>
```

**Modal** (Image Viewer):
```html
<div class="modal" id="imageModal">
  <div class="modal-content">
    <span class="close">&times;</span>
    <img src="" id="modalImage">
  </div>
</div>
```

---

## 🔐 Authentication (Optional)

**Login Page** (`login.php`):
```html
<form action="/api/login" method="POST">
  <input type="text" name="username" placeholder="Username">
  <input type="password" name="password" placeholder="Password">
  <button type="submit">Login</button>
</form>
```

**Session Management**:
```php
<?php
session_start();
if (!isset($_SESSION['user_id'])) {
    header('Location: login.php');
    exit;
}
?>
```

---

## ✅ Features Summary

- ✅ Real-time dashboard
- ✅ Advanced filtering & search
- ✅ Image viewer (full + cropped)
- ✅ OCR voting history display
- ✅ Quality metrics visualization
- ✅ Camera management
- ✅ Statistics & charts
- ✅ Export reports (CSV/PDF)
- ✅ Responsive design (mobile-friendly)
- ✅ Auto-refresh data

---

**Tech Stack**: HTML/CSS/JavaScript + PHP + Bootstrap/Tailwind + Chart.js + Leaflet.js
