# API backend v2-test

`v2-test` là namespace tài liệu dành riêng cho test camera và model detect. `v1` vẫn là API chính.

## 1. Mục tiêu

`v2-test` chỉ dùng để:

- test camera gửi ảnh có lên backend hay không
- test model detect/OCR có chạy đúng không
- đo thời gian xử lý
- xem output kỹ thuật để debug

`v2-test` không dùng để:

- tạo violation chính thức
- ghi dữ liệu nghiệp vụ vào `violations`
- thay thế `v1`

## 2. Nguyên tắc thiết kế

- namespace riêng: `/api/v2-test`
- output rõ, giàu thông tin kỹ thuật
- có thể bật hoặc tắt OCR
- không ghi cơ sở dữ liệu nghiệp vụ
- chỉ phục vụ test camera và model detect

## 3. Đề xuất endpoint tối thiểu

### `GET /api/v2-test/health`

Tác dụng:

- kiểm tra module test đang sẵn sàng
- trả version model và trạng thái dependency

Response mẫu:

```json
{
  "status": "ok",
  "service": "v2-test",
  "detector_ready": true,
  "ocr_ready": true,
  "timestamp": "2026-03-09T10:00:00"
}
```

### `POST /api/v2-test/detect/frame`

Tác dụng:

- test một frame đơn
- không ghi DB
- trả detect + OCR + quality

Request:

- `multipart/form-data`

Field:

- `file`: ảnh
- `camera_id`: không bắt buộc
- `run_ocr`: boolean, mặc định `true`
- `save_debug_image`: boolean, mặc định `false`

Response mẫu:

```json
{
  "success": true,
  "camera_id": 1,
  "quality_score": 84.2,
  "processing_ms": 196,
  "detections": [
    {
      "bbox": {
        "x1": 120,
        "y1": 80,
        "x2": 260,
        "y2": 140
      },
      "plate_text": "51A12345",
      "confidence": 0.91,
      "ocr_confidence": 0.88
    }
  ],
  "debug": {
    "model": "LP_detector_nano_61.pt",
    "ocr_enabled": true
  }
}
```

### `POST /api/v2-test/detect/batch`

Tác dụng:

- test nhiều frame liên tiếp
- đánh giá độ ổn định detect và OCR
- không tạo violation

Request:

- `multipart/form-data`
- nhiều file cùng field `files`

Response mẫu:

```json
{
  "success": true,
  "frames_total": 5,
  "frames_processed": 5,
  "avg_quality_score": 79.6,
  "results": []
}
```

### `GET /api/v2-test/models`

Tác dụng:

- trả danh sách model đang dùng
- giúp test đúng phiên bản file model

Response mẫu:

```json
{
  "detector_model": "LP_detector_nano_61.pt",
  "ocr_model": "LP_ocr_nano_62.pt"
}
```

## 4. Phạm vi test nên giữ gọn

Chỉ test các phần sau:

- camera upload được ảnh
- ảnh decode được
- quality score
- detect biển số
- OCR text
- thời gian xử lý

Không nên nhét vào `v2-test`:

- CRUD camera
- CRUD zone
- dashboard stats
- finalize violation
- logic nghiệp vụ red-light

## 5. Cách dùng thực tế

### Test camera từ máy tính

1. chụp một ảnh mẫu
2. gọi `POST /api/v2-test/detect/frame`
3. xem `quality_score`, `detections`, `plate_text`

### Test camera từ ESP32

1. ESP32 gửi thử frame tới `v2-test`
2. backend trả output kỹ thuật
3. nếu ổn mới chuyển sang `v1 /api/upload`

## 6. Trạng thái hiện tại

Tài liệu này là chuẩn thiết kế.

Hiện tại:

- code chưa implement namespace `/api/v2-test`
- nên tạo sau khi chuẩn hóa xong `v1`
