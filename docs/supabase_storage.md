# Tài liệu: Supabase Storage — Lưu ảnh vi phạm

## Tổng quan

Hệ thống lưu ảnh vi phạm theo chiến lược **local-first → cloud-backup**:

| Bước | Hành động | Thời gian |
|------|-----------|-----------|
| 1 | Ghi ảnh ra đĩa local | ~5ms (ngay lập tức) |
| 2 | Ghi bản ghi `violations` vào Supabase DB (URL local) | ~100ms |
| 3 | Upload ảnh lên Supabase Storage (background task) | ~300–2000ms |
| 4 | Cập nhật URL trong bảng `violations` → CDN URL | ~100ms |

## Thông tin Bucket

| Thông số | Giá trị |
|----------|---------|
| Tên Bucket | `Camera AI` |
| Loại | **PUBLIC** (không cần xác thực để xem ảnh) |
| Dung lượng tối đa / file | 50 MB (mặc định Supabase free) |
| Project URL | `https://hfnyjmdloozduyrlgnht.supabase.co` |

## Cấu trúc thư mục trong Bucket

```
Camera AI/
├── violations/
│   ├── vehicle_cam1_20260319_142500_a3f1b2.jpg   ← ảnh crop xe
│   └── scene_cam1_20260319_142500_d9e2c1.jpg     ← ảnh toàn cảnh
└── plates/
    └── plate_cam1_20260319_142500_f4a8e5.jpg      ← ảnh crop biển số
```

## Format tên file

```
{loại}_cam{camera_id}_{YYYYMMDD}_{HHMMSS}_{microseconds}_{uid6}.jpg
```

Ví dụ: `vehicle_cam2_20260319_142157_123456_a3f1b2.jpg`

## URL của ảnh sau khi upload

### Dạng URL Supabase CDN (Public Bucket)
```
https://hfnyjmdloozduyrlgnht.supabase.co/storage/v1/object/public/Camera%20AI/{folder}/{filename}
```

### Ví dụ URL thực tế

| Loại ảnh | URL |
|----------|-----|
| Ảnh toàn cảnh | `https://hfnyjmdloozduyrlgnht.supabase.co/storage/v1/object/public/Camera%20AI/violations/scene_cam1_xxx.jpg` |
| Ảnh xe (crop) | `https://hfnyjmdloozduyrlgnht.supabase.co/storage/v1/object/public/Camera%20AI/violations/vehicle_cam1_xxx.jpg` |
| Biển số (crop) | `https://hfnyjmdloozduyrlgnht.supabase.co/storage/v1/object/public/Camera%20AI/plates/plate_cam1_xxx.jpg` |

> ⚠️ **Lưu ý URL Encoding:** Tên bucket `Camera AI` khi dùng trong URL phải encode thành `Camera%20AI`.

## Trường URL trong bảng `violations`

| Cột DB | Nội dung | Upload field |
|--------|----------|-------------|
| `full_image_url` | Ảnh toàn cảnh lúc vi phạm | `full_image_url` |
| `cropped_plate_url` | Ảnh crop biển số | `cropped_plate_url` |
| `cropped_vehicle_url` | Ảnh crop toàn xe | `cropped_vehicle_url` |

**Giá trị URL theo thời gian:**

```
T+0ms   (local):  http://192.168.1.80:8000/uploads/violations/scene_cam1_xxx.jpg
T+500ms (cloud):  https://hfnyjmdloozduyrlgnht.supabase.co/storage/v1/object/public/Camera%20AI/violations/scene_cam1_xxx.jpg
```

## Cấu hình trong `.env`

```env
# Tên bucket (phải là PUBLIC bucket)
SUPABASE_STORAGE_BUCKET=Camera AI

# true = upload cloud, false = chỉ giữ local  
STORAGE_UPLOAD_ENABLED=true
```

## Cách xem/quản lý file trên Dashboard Supabase

1. Truy cập: [https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht/storage/buckets](https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht/storage/buckets)
2. Chọn bucket **Camera AI**
3. Browse thư mục `violations/` hoặc `plates/`

## Các file liên quan

| File | Vai trò |
|------|---------|
| [`image_service.py`](file:///c:/Users/Phucc/Desktop/ytd/backend/services/image_service.py) | Logic lưu ảnh + upload Supabase |
| [`settings.py`](file:///c:/Users/Phucc/Desktop/ytd/backend/config/settings.py) | Cấu hình `supabase_storage_bucket`, `storage_upload_enabled` |
| [`violation_engine.py`](file:///c:/Users/Phucc/Desktop/ytd/backend/services/violation_engine.py) | Gọi `ImageService` để lưu ảnh bằng chứng |
| [`violation_service.py`](file:///c:/Users/Phucc/Desktop/ytd/backend/services/violation_service.py) | Ghi URL vào bảng `violations` |

## Xử lý lỗi & Fallback

| Tình huống | Xử lý |
|------------|-------|
| Mất mạng khi upload | Giữ local URL, log cảnh báo, **không crash** |
| Upload thất bại | URL trong DB vẫn là local URL, ảnh vẫn xem được qua backend |
| Local disk đầy | `cv2.imwrite` fail → trả `None` → violate không có ảnh (có log) |
| Supabase service down | Background task fail → log, URL giữ nguyên local |
