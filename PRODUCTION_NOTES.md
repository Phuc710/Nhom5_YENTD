# PRODUCTION NOTES

## 1) Phần production (dùng dữ liệu thật)

- `server/app.py`
  - Backend FastAPI trung tâm.
  - API đọc/ghi camera, violation, heartbeat từ DB thật (`traffic_ai.db`).
  - SSE realtime từ backend (`/api/realtime/events`).

- `server/ai_engine.py`
  - Pipeline AI thật: detect/OCR -> lưu ảnh thật vào `imge/violations/...` -> gửi `POST /api/violations`.
  - Không ghi violation fake từ frontend.

- `DEVELOPER/main.js`
  - Đã bỏ nhánh inject violation giả (`inject_violation`).
  - Không dùng fallback camera hardcode (`LAPTOP_CAM_001`) cho stream.
  - Không dùng fallback device list hardcode.
  - Lookup UI chỉ hiển thị kết quả DB backend (không hiển thị sample CSV).

- `DEVELOPER/login.js`
  - Legacy fallback credentials đã tắt.
  - Runtime status wording đã đổi theo production (connected/standby/offline), không mô tả sim path.

## 2) Phần test/integration (tách riêng)

- `server/virtual_esp32_cluster.py`
  - Simulator heartbeat cho integration test.
  - Có safety gate bắt buộc `--integration-test` để tránh chạy nhầm production.

- `server/csv_importer.py`
  - Tool import/export phục vụ migration/test dữ liệu.
  - `sample_violations.csv` được đánh dấu test-only:
    - Import sample bị chặn nếu không có `--allow-test-data` (hoặc env `TRAFFIC_ALLOW_TEST_DATA=1`).
    - Generate sample bị chặn nếu không có `--allow-test-data`.
  - `get_reference_rows()` chỉ đọc sample khi bật `TRAFFIC_ALLOW_TEST_DATA=1`.

- `server/sample_violations.csv`
  - Chỉ dùng cho test/migration.
  - Không dùng trực tiếp để render UI production.

- `server/main.py`
  - Entrypoint standalone cho bài toán đếm xe/video experiment.
  - Không phải backend production runtime.

## 3) Cách chạy production mode

1. Backend:
   - `cd server`
   - `python app.py`

2. Frontend:
   - Mở qua backend routes (`/main`, `/login`, `/index`), không mở file HTML rời.

3. AI service:
   - `cd server`
   - `python ai_engine.py`

4. Không bật test-mode trong production:
   - Không chạy `virtual_esp32_cluster.py`.
   - Không import `sample_violations.csv`.
   - Không set `TRAFFIC_ALLOW_TEST_DATA=1`.

## 4) Cách chạy integration test (khi cần)

- Simulator heartbeat:
  - `python server/virtual_esp32_cluster.py --integration-test --transport http --count 12`
- Nếu cần test sample CSV:
  - `python server/csv_importer.py import server/sample_violations.csv --allow-test-data`
