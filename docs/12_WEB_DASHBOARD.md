# Web Dashboard

## 📄 Pages

### 1. Dashboard (`index.php`)

**Layout**:
```
┌──────────────────────────────┐
│ Stats Cards                  │
│ ┌────┬────┬────┬────┐       │
│ │Total│Day│Week│30d│       │
│ └────┴────┴────┴────┘       │
├──────────────────────────────┤
│ Charts (violations over time)│
├──────────────────────────────┤
│ Recent 10 violations         │
└──────────────────────────────┘
```

**API**: `GET /api/stats`, `GET /api/violations?limit=10`

### 2. Violations List (`violations.php`)

**Features**:
- Filters: camera, date range, plate
- Table: ID, plate, location, time, actions
- Pagination: 20/page

**API**: `GET /api/violations?camera_id=1&date_from=...&plate=...`

### 3. Violation Detail (`violation_detail.php?id=123`)

**Display**:
- Full image + cropped plate
- Metadata: plate, confidence, quality, timestamp, location
- OCR voting history (debug table)
- Map (Leaflet.js)

**API**: `GET /api/violations/123`

### 4. Camera Management (`cameras.php`)

**Features**:
- List cameras: ID, name, location, status
- Edit camera settings

**API**: `GET /api/cameras`, `PUT /api/cameras/{id}`

---

## 🎨 Tech Stack

- **Frontend**: HTML + Bootstrap + Chart.js
- **Maps**: Leaflet.js
- **Auto-refresh**: 30s interval

---

## 📋 Sample Code

```html
<!-- Dashboard stats -->
<div class="card">
  <h3>Total Violations</h3>
  <p id="total">0</p>
</div>

<script>
fetch('/api/stats')
  .then(r => r.json())
  .then(data => {
    document.getElementById('total').textContent = data.total;
  });
</script>
```
