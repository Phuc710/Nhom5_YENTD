Kế hoạch Hệ thống Quản lý Vi phạm Giao thông
Tổng quan
Hệ thống 3 tầng: ESP32-S3-CAM → FastAPI Backend → PHP Frontend
Database: Supabase (PostgreSQL). Múi giờ: Asia/Ho_Chi_Minh (UTC+7).

Cấu trúc thư mục
ytd/
├── backend/                # FastAPI (Python)
│   ├── .env                # secrets (không commit)
│   ├── .env.example        # template
│   ├── main.py             # entry point
│   ├── config/settings.py  # OOP Settings từ .env
│   ├── database/
│   │   └── supabase_client.py
│   ├── models/             # Pydantic schemas
│   │   ├── camera.py
│   │   ├── violation.py
│   │   └── zone.py
│   ├── repositories/       # DB layer (OOP)
│   │   ├── camera_repo.py
│   │   ├── violation_repo.py
│   │   └── zone_repo.py
│   ├── services/           # Business logic (OOP)
│   │   ├── camera_service.py
│   │   ├── violation_service.py
│   │   ├── zone_service.py
│   │   └── provision_service.py  # NEW: sync TB → DB
│   ├── api/                # FastAPI routers
│   │   ├── cameras.py      # CRUD camera + provision sync
│   │   ├── violations.py   # Vi phạm
│   │   ├── zones.py        # NEW: Zone detection config
│   │   ├── upload.py       # Nhận frame từ ESP32
│   │   └── stats.py        # Thống kê
│   └── requirements.txt
│
├── frontend/               # PHP + HTML + CSS + JS
│   ├── .env                # config frontend
│   ├── config.php          # đọc .env, constants
│   ├── index.php           # Dashboard (card cameras)
│   ├── camera.php          # Chi tiết camera + stream + zones
│   ├── violations.php      # Lịch sử vi phạm
│   ├── violation-detail.php# Chi tiết 1 vi phạm
│   ├── assets/
│   │   ├── css/
│   │   │   ├── main.css        # base, variables, layout
│   │   │   ├── dashboard.css   # trang chủ
│   │   │   ├── camera.css      # trang camera
│   │   │   ├── violations.css  # bảng vi phạm
│   │   │   └── zone-editor.css # canvas zone drawing
│   │   ├── js/
│   │   │   ├── api.js          # fetch wrapper, base URL
│   │   │   ├── dashboard.js    # load cameras, stats
│   │   │   ├── camera.js       # stream, zone load/save
│   │   │   ├── zone-editor.js  # drag/resize/draw zones
│   │   │   └── violations.js   # filter, pagination
│   │   └── img/
│   │       └── logo.svg
│   └── includes/
│       ├── header.php      # nav, meta
│       └── footer.php      # scripts
│
├── database/
│   └── schema.sql          # Supabase schema
│
├── run.py                  # Launcher: backend + frontend
└── docker-compose.yml      # ThingsBoard + Mosquitto
Database Schema — Bổ sung
Bảng mới: detection_zones
sql
CREATE TABLE detection_zones (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id   INTEGER NOT NULL REFERENCES cameras(camera_id),
    zone_name   VARCHAR(100) NOT NULL,
    x           INTEGER NOT NULL,
    y           INTEGER NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    zone_type   VARCHAR(50) DEFAULT 'detection',  -- detection | stop_line
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
Bảng mới: camera_provisioning
Lưu thông tin provisioning từ ThingsBoard:

sql
CREATE TABLE camera_provisioning (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    camera_id       INTEGER UNIQUE REFERENCES cameras(camera_id),
    tb_device_id    VARCHAR(255),
    access_token    VARCHAR(255),
    mac_address     VARCHAR(20),
    fw_version      VARCHAR(50),
    last_seen_at    TIMESTAMPTZ,
    ip_address      VARCHAR(45),
    provisioned_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
Cập nhật cameras:
Thêm stream_url (RTSP/HTTP stream từ ESP32)
Thêm description
Thêm tb_device_name
API Endpoints mới/cập nhật
Method	Path	Mô tả
GET	/api/cameras	Danh sách camera + trạng thái
GET	/api/cameras/{id}	Chi tiết camera
POST	/api/cameras/{id}/provision	Sync provisioning từ TB → DB
GET	/api/cameras/{id}/zones	Lấy zones của camera
PUT	/api/cameras/{id}/zones	Lưu toàn bộ zones (replace)
GET	/api/violations	Danh sách vi phạm (filter, page)
GET	/api/violations/{id}	Chi tiết vi phạm
POST	/api/ocr/kafka	Nhận frame từ ESP32 (existing)
GET	/api/stats/summary	Stats tổng quan dashboard
Frontend Pages
index.php — Dashboard
Stats cards: tổng vi phạm hôm nay, BSX phát hiện, cameras online
Cards camera: ảnh thumbnail, trạng thái, vị trí, số vi phạm hôm nay
Bảng 10 vi phạm gần nhất
camera.php?id={camera_id} — Chi tiết Camera
Live stream từ ESP32 (<img src="http://esp-ip/stream">)
Canvas Zone Editor (phủ lên stream, drag/resize/vẽ zone)
Lịch sử vi phạm của camera đó
Thông tin thiết bị: firmware, MAC, IP, last seen
violations.php — Lịch sử Vi phạm
Filter: camera, ngày, BSX
Bảng: ảnh thumbnail, BSX, thời gian, vị trí, confidence
Pagination
violation-detail.php?id={id} — Chi tiết Vi phạm
Ảnh full size (xe đang vượt đèn đỏ)
Ảnh cropped biển số với BSX overlay
Thông tin: BSX, thời gian (+7), vị trí camera, trạng thái đèn
Box highlight vị trí xe trên ảnh full
Zone Editor (JS)
Canvas phủ lên <img> stream
Click + drag → vẽ box mới
Drag box → di chuyển
Drag handle góc → resize
Label zone name
JSON preview
Nút Save → PUT /api/cameras/{id}/zones
Cấu hình bảo mật
Backend: 
backend/.env
 (SUPABASE_URL, SUPABASE_KEY, etc.)
Frontend: frontend/.env (API_URL, etc.)
Không commit 
.env
, chỉ commit 
.env.example
run.py
Khởi động cả 2 process: uvicorn backend + PHP built-in server

python
subprocess.Popen(["uvicorn", "main:app", ...], cwd="backend")
subprocess.Popen(["php", "-S", "0.0.0.0:8080"], cwd="frontend")