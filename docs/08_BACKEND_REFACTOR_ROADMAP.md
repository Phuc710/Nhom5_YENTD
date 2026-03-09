# Lộ trình refactor backend

Tài liệu này trả lời câu hỏi: phải sửa từ đâu đến đâu để đồng bộ toàn bộ backend.

## 1. Thứ tự làm chuẩn

### Bước 1: chốt tài liệu và naming

File cần bám:

- [`00_BACKEND_DOCS_INDEX.md`](/c:/Users/Phucc/Desktop/ytd/docs/00_BACKEND_DOCS_INDEX.md)
- [`02_BACKEND_API_V1.md`](/c:/Users/Phucc/Desktop/ytd/docs/02_BACKEND_API_V1.md)
- [`03_BACKEND_API_V2_TEST.md`](/c:/Users/Phucc/Desktop/ytd/docs/03_BACKEND_API_V2_TEST.md)

Mục tiêu:

- không sửa code khi chưa chốt hợp đồng API
- không thêm endpoint ngẫu hứng

### Bước 2: đóng băng `v1`

Việc cần làm:

- giữ nguyên endpoint `v1` đang dùng bởi frontend
- đánh dấu endpoint nào là chính, endpoint nào là phụ hoặc legacy

File liên quan:

- [`backend/api/cameras.py`](/c:/Users/Phucc/Desktop/ytd/backend/api/cameras.py)
- [`backend/api/upload.py`](/c:/Users/Phucc/Desktop/ytd/backend/api/upload.py)
- [`backend/api/finalize.py`](/c:/Users/Phucc/Desktop/ytd/backend/api/finalize.py)
- [`backend/api/violations.py`](/c:/Users/Phucc/Desktop/ytd/backend/api/violations.py)
- [`backend/api/stats.py`](/c:/Users/Phucc/Desktop/ytd/backend/api/stats.py)

### Bước 3: dọn namespace stats

Vấn đề hiện tại:

- `/api/stats/*` và `/api/violations/stats/*` bị trùng vai trò

Việc cần làm:

- chọn một namespace chuẩn
- namespace còn lại chỉ giữ tương thích tạm thời hoặc bỏ sau

### Bước 4: tách pipeline nghiệp vụ và pipeline test

Việc cần làm:

- `v1`: tạo violation thật
- `v2-test`: chỉ test camera + detect model + OCR

File sẽ tạo hoặc sửa:

- `backend/api/upload.py`
- `backend/services/image_service.py`
- `backend/ml/detector.py`

### Bước 5: thêm rule engine zone

Đây là bước quan trọng nhất để đúng nghiệp vụ.

Việc cần làm:

1. đọc zone theo `camera_id`
2. map bbox của object vào zone
3. xác định cắt `stop_line`
4. kết hợp `traffic_light_state`
5. chỉ khi đúng rule mới tạo violation

File nên tạo hoặc sửa:

- `backend/services/finalize_service.py`
- `backend/services/tracking_service.py`
- `backend/services/violation_service.py`
- có thể thêm mới `backend/services/zone_rule_service.py`

### Bước 6: chuẩn hóa response schema

Việc cần làm:

- chọn chuẩn response cho `v2-test`
- chưa ép `v1` đổi format nếu frontend đang dùng
- nếu refactor sâu thì tạo response model chung

### Bước 7: đồng bộ frontend

Sau khi backend ổn mới sửa frontend.

Frontend cần đồng bộ:

- API URL
- stats endpoint chuẩn
- camera detail
- zone editor
- hiển thị trạng thái đèn

## 2. Việc nên làm ngay

Nếu muốn sửa theo thứ tự ít rủi ro nhất, hãy làm ngay các mục sau:

1. dọn tài liệu và naming
2. chốt API `v1`
3. tạo `v2-test`
4. viết rule engine `zone + stop_line + traffic_light_state`

## 3. Việc chưa nên làm ngay

- chưa đổi tên hàng loạt endpoint `v1`
- chưa sửa frontend trước khi backend chốt
- chưa merge `v2-test` vào luồng nghiệp vụ

## 4. Kết luận

Thứ tự sửa đồng bộ nên là:

1. docs
2. API contract
3. test API
4. zone rule engine
5. response cleanup
6. frontend sync
