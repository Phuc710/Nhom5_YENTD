# Cấu Trúc Project

```
ytd/
├── backend/                    # Python FastAPI Server
│   ├── api/                    # REST API endpoints
│   │   ├── upload.py          # Upload ảnh từ ESP32
│   │   ├── violations.py      # CRUD vi phạm
│   │   ├── cameras.py         # Quản lý camera
│   │   └── stats.py           # Thống kê
│   ├── ml/                     # YOLO Models
│   │   ├── detector.py        # License plate detector
│   │   ├── LP_detector_nano_61.pt
│   │   └── LP_ocr_nano_62.pt
│   ├── services/               # Business Logic
│   │   ├── violation_service.py
│   │   ├── image_service.py
│   │   ├── camera_service.py
│   │   └── stats_service.py
│   ├── database/               # Database
│   │   ├── supabase_client.py
│   │   └── models.py
│   ├── config/
│   │   └── settings.py
│   ├── uploads/                # Uploaded Images
│   │   ├── original/          # Ảnh gốc
│   │   └── detected_plates/   # Ảnh biển số crop
│   ├── main.py                 # Entry point
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                   # Web Dashboard
│   ├── index.php              # Trang chính
│   ├── detail.php             # Chi tiết vi phạm
│   ├── css/
│   │   └── style.css          # Clean CA-style UI
│   └── js/
│       ├── config.js          # API config
│       ├── api.js             # API wrapper
│       ├── dashboard.js       # Dashboard logic
│       └── detail.js          # Detail page logic
│
├── esp32-cam/                  # ESP32-CAM Firmware
│   ├── include/               # Header files
│   │   ├── config.h           # ⚠️ Main config
│   │   ├── camera.h
│   │   ├── network.h
│   │   ├── upload.h
│   │   └── ota.h
│   ├── src/                   # Source files
│   │   ├── main.cpp
│   │   ├── camera.cpp
│   │   ├── network.cpp
│   │   ├── upload.cpp
│   │   └── ota.cpp
│   ├── platformio.ini
│   └── partitions.csv         # Dual OTA partitions
│
├── esp32-traffic-light/        # ESP32 Traffic Light
│   ├── include/
│   │   └── config.h           # ⚠️ Main config
│   ├── src/
│   │   └── main.cpp
│   └── platformio.ini
│
├── database/                   # SQL Schemas
│   └── schema.sql             # Supabase tables
│
├── docs/                       # Documentation (Tiếng Việt)
│   ├── 01_KIEN_TRUC.md       # Architecture
│   ├── 02_DEPLOY_BACKEND.md  # Backend deployment
│   ├── 03_CAI_DAT_ESP32_CAM.md
│   ├── 04_DEN_GIAO_THONG.md
│   ├── 05_THINGSBOARD.md
│   ├── 08_TEST_API.md
│   └── 09_OTA_DUAL_PARTITION.md
│
├── README.md                   # Main documentation
└── GETTING_STARTED.md         # Quick start guide
```

## Files Quan Trọng

### Cấu Hình

| File | Mô tả |
|------|-------|
| `backend/.env` | Supabase credentials, settings |
| `esp32-cam/include/config.h` | Backend URL, ThingsBoard keys |
| `esp32-traffic-light/include/config.h` | ThingsBoard token, timing |
| `frontend/js/config.js` | Backend API URL |

### Entry Points

| File | Mô tả |
|------|-------|
| `backend/main.py` | FastAPI server |
| `frontend/index.php` | Web dashboard |
| `esp32-cam/src/main.cpp` | ESP32-CAM firmware |
| `esp32-traffic-light/src/main.cpp` | Traffic light firmware |

## Tổng Số Files

- **Backend**: ~20 files
- **Frontend**: ~8 files
- **ESP32-CAM**: ~12 files
- **ESP32 Traffic Light**: ~3 files
- **Database**: 1 file
- **Docs**: 7 files
- **Total**: ~51 files

