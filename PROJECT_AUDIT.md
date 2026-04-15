# PROJECT AUDIT - WEB DEVELOPER (2026-04-15)

## 1) Kien truc hien tai (as-is)

- Kieu kien truc: **monolith Flask + Socket.IO + MQTT + SQLite + frontend static**.
- Backend runtime chinh: `server/app.py` (125 routes, websocket events, mqtt client, db init/migration, traffic controller, camera/laptop feed, ai hook, file serving).
- Frontend runtime chinh: `DEVELOPER/main.html` + `DEVELOPER/main.js` + `DEVELOPER/main.css`.
- Auth flow: `index.html` (boot) -> `login.html/login.js` -> `main.html/main.js`, token luu localStorage.
- AI/vision hien tai: `app.py` + `ai_engine.py` + `image_processor.py` (YOLO + EasyOCR).
- MQTT/hardware layer: `app.py` + `virtual_esp32_cluster.py` + `start_mqtt.bat` + `mosquitto.conf`.
- Data layer: `traffic_ai.db` (runtime), `schema.sql` (base schema), `seed_database.py` + `sample_violations.csv` (seed/demo).

## 2) Vai tro tung file + danh gia su dung

| File | Vai tro hien tai | Phan loai | Khuyen nghi |
|---|---|---|---|
| `DEVELOPER/index.html` | Boot screen, health/bootstrap check, redirect login/main | Frontend boot | **Giu** |
| `DEVELOPER/login.css` | Style login + boot/login visual system | Frontend style | **Refactor nhe** (tach module/theme) |
| `DEVELOPER/login.html` | Trang login, render auth UI | Frontend auth | **Giu** |
| `DEVELOPER/login.js` | Login logic `/api/login`, lockout, remember, UI effects | Frontend auth logic | **Refactor** (tach auth core va ui effects) |
| `DEVELOPER/main.css` | Dashboard style (rat lon, all-in-one) | Frontend style | **Refactor** (chia file theo section) |
| `DEVELOPER/main.html` | Dashboard shell + section layout | Frontend main | **Giu** |
| `DEVELOPER/main.js` | Toan bo dashboard logic (API, socket, traffic, camera, TB, ACL...) | Frontend main logic | **Refactor manh** (tach module) |
| `server/ai_engine.py` | Worker AI doc camera + publish MQTT context; duoc `app.py` import `start_ai` | AI service helper | **Refactor/merge** (xac dinh ro worker rieng hay nhung trong app) |
| `server/app.py` | Backend chinh: API, WS, MQTT, DB, static files, bootstrap | **Backend chinh** | **Refactor manh** (chia module/service) |
| `server/config.env` | Runtime config local | Config runtime | **Giu** (nhung can dong bo key voi code) |
| `server/config.example.env` | Template env cho setup moi | Config template | **Giu** (cap nhat key dung) |
| `server/csv_importer.py` | Import/export violations CSV, script tool | Data tool | **Giu** |
| `server/image_processor.py` | Detect/OCR/snapshot helper + DB save | AI processing tool | **Giu + refactor nhe** |
| `server/main.py` | Entrypoint cuc cu cho `configs/` + `src/vehicle_counter` | Legacy/demo path | **Khong nen dung nua** (deprecate) |
| `server/mosquitto.conf` | Local MQTT broker config | MQTT infra | **Giu** |
| `server/requirements.txt` | Python dependencies backend/AI | Dependency manifest | **Giu** |
| `server/sample_violations.csv` | Du lieu mau violation | Du lieu gia lap | **Giu** |
| `server/schema.sql` | Base DB schema + seed defaults | DB schema | **Refactor** (dong bo voi DB runtime) |
| `server/seed_database.py` | Seed data mau vao SQLite | Demo/mock data tool | **Giu** |
| `server/start_mqtt.bat` | Start local Mosquitto | MQTT startup | **Giu** |
| `server/start_server.bat` | Start backend `app.py` + dependency check | Backend startup | **Giu** (bo sung support host/port env) |
| `server/traffic_controller.py` | Traffic light runtime/profile state machine | Domain service | **Giu** |
| `server/traffic_data.yaml` | Dataset config train YOLO | AI training data config | **Giu** |
| `server/train_model.py` | Train/validate/export YOLO | AI training tool | **Giu** |
| `server/virtual_esp32_cluster.py` | Mo phong ESP32-CAM cluster + frame/context/violation MQTT | Simulator/mock hardware | **Giu** |
| `server/yolov8n.pt` | Base YOLO model fallback | AI model artifact | **Giu** |
| `CAMERA_DASHBOARD_2026_STACK.md` | Deployment notes/mo rong stack (MERN/edge/infra) | Tai lieu roadmap | **Giu** |
| `server/traffic_ai.db` | DB runtime hien tai | Runtime data | **Giu** |
| `server/traffic_ai_backup_20260311_141027.db` | Ban backup DB cu | Backup/archival | **Khong runtime** (chi backup) |

## 3) Xac dinh nhanh theo nhom ban yeu cau

- Backend chinh: **`server/app.py`** (duoc goi boi `server/start_server.bat`).
- Frontend chinh: **`DEVELOPER/main.html` + `main.js` + `main.css`**.
- AI service: **`server/ai_engine.py`** (runtime thread), + helper trong `app.py` va `image_processor.py`.
- MQTT logic: **`app.py` (`_init_mqtt`, `_on_mqtt_message`, publish/subscribe)** + `virtual_esp32_cluster.py`.
- Du lieu gia lap: **`sample_violations.csv`**, seed du lieu trong `seed_database.py`.
- Code demo/mock/simulator: **`virtual_esp32_cluster.py`**, `seed_database.py`, `csv_importer.py` (tooling), `main.py` (legacy demo path).

## 4) Van de hien tai (quan trong)

1. **Monolith qua lon**: `app.py` ~288KB, gom qua nhieu concern (API + WS + MQTT + DB + static + AI bootstrap).
2. **Frontend JS qua lon/khong tach module**: `main.js` ~269KB, co duplicate function (`ensureToken`, `_tbSetBadge`) va doan unreachable code sau `return`.
3. **Lech cau hinh env va code**:
   - `DB_PATH`, `HOST`, `PORT`, `TOKEN_TTL` trong `config.env` khong duoc app su dung dung cach (app hardcode DB path, host/port, `_TOKEN_TTL`).
4. **Schema drift** giua `schema.sql` va DB runtime:
   - Co trong schema nhung khong co trong DB: `ai_context`, `audit_log`, `thingboard_sync`.
   - Co trong DB nhung khong co trong schema: `context_snapshots`, `system_events`, `theme_preferences`, `device_telemetry`.
5. **Encoding/charset bi vo (mojibake)** o nhieu file (`config.env`, `schema.sql`, `sample_violations.csv`, comments).
6. **Auth flow frontend co dau hieu tech debt**: hardcoded token constant trong client + guard/fallback logic trung lap.
7. **Nhieu phien ban kien truc song song**: `main.py` (legacy counter pipeline) va `app.py` (current production-like monolith).

## 5) Huong nang cap len he thong that

- Tach backend thanh 4 khoi ro rang:
  - `api-service` (auth, incidents, camera CRUD, reports)
  - `realtime-gateway` (socket + mqtt bridge)
  - `ai-worker` (yolo/ocr processing, batch queue)
  - `simulator-service` (virtual esp32, optional)
- Chuyen DB tu SQLite runtime sang PostgreSQL (SQLite giu local-dev).
- Chuan hoa config bang 1 layer typed settings (khong hardcode host/port/db path).
- Tach frontend theo modules (`auth`, `traffic`, `camera`, `violations`, `thingsboard`, `acl`).
- Dung migration tool (Alembic) de khong drift schema.
- Chuan hoa observability: structured logs, health/readiness, metrics endpoint tach rieng.
- Dinh ro che do `real` vs `simulator` bang feature flags server-side.

## 6) Danh sach file can sua o giai doan tiep theo

### Uu tien P1 (can xu ly som)
- `server/app.py`
- `DEVELOPER/main.js`
- `server/config.env`
- `server/config.example.env`
- `server/schema.sql`

### Uu tien P2
- `DEVELOPER/main.css`
- `DEVELOPER/login.js`
- `server/ai_engine.py`
- `server/image_processor.py`
- `server/start_server.bat`

### Uu tien P3
- `server/main.py` (deprecate/di chuyen archive)
- `server/seed_database.py`
- `server/csv_importer.py`
- `server/traffic_data.yaml` (encoding + clarity)
- `CAMERA_DASHBOARD_2026_STACK.md` (dong bo voi implementation that)

## 7) Ghi chu kiem chung audit

- Da doc va doi chieu toan bo file duoc yeu cau.
- Da kiem tra DB runtime va backup (table + so luong record).
- Khong thay doi bat ky file hien co; chi tao moi file bao cao nay.
