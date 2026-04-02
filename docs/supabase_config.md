# Hướng dẫn Cấu hình Supabase Realtime & Storage

Tài liệu này hướng dẫn cách cấu hình Supabase để backend hoạt động chuẩn xác với các tính năng Realtime và Storage.

## 1. Kích hoạt Realtime cho Bảng (Tables)

Để Backend có thể "nghe" thấy các thay đổi từ Database (ví dụ: khi anh sửa tên Camera trên web), anh cần bật Realtime cho các bảng tương ứng.

**Các bước thực hiện:**
1. Truy cập [Supabase Dashboard](https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht).
2. Vào mục **Database** (biểu tượng hình trụ) ở cột bên trái.
3. Chọn **Replication**.
4. Trong phần **Supabase Realtime**, nhấn vào liên kết **'X tables'** (ví dụ: '0 tables' hoặc '2 tables').
5. Gạt nút **ON** cho các bảng sau:
   - `cameras`
   - `camera_provisioning`

> [!IMPORTANT]
> Nếu không bật Realtime cho các bảng này, backend sẽ báo lỗi: `Unable to subscribe to changes...`

---

## 2. Cấu hình Storage (Bucket)

Hệ thống lưu ảnh vi phạm lên Supabase Storage để anh có thể xem từ bất cứ đâu.

**Thông tin Storage:**
- **Bucket Name:** `Camera AI`
- **Access Level:** `Public`

**Các bước kiểm tra:**
1. Vào mục **Storage** (biểu tượng hộp) ở cột bên trái.
2. Kiểm tra xem đã có bucket tên là `Camera AI` chưa.
3. Nếu chưa, hãy tạo mới với tên chính xác là `Camera AI` và tích chọn **Public bucket**.
4. Backend sẽ tự động upload ảnh vào các thư mục:
   - `violations/`: Chứa ảnh toàn cảnh và ảnh xe.
   - `plates/`: Chứa ảnh biển số đã cắt.

---

## 3. Đường dẫn (Links) quan trọng

| Tài nguyên | Đường dẫn |
| :--- | :--- |
| **Bảng điều khiển Supabase** | [Trang chủ dự án](https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht) |
| **Quản lý File ảnh** | [Storage -> Camera AI](https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht/storage/files/buckets/Camera%20AI) |
| **Dữ liệu Camera** | [Table Editor -> cameras](https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht/editor/table/126837718) |
| **Dữ liệu Vi phạm** | [Table Editor -> violations](https://supabase.com/dashboard/project/hfnyjmdloozduyrlgnht/editor/table/violations) |

---

## 4. Kiểm tra Backend Logs

Khi mọi thứ chuẩn xác, anh sẽ thấy log ở Backend như sau:

```text
✅ Identity cache: nạp xong X MAC, Y TB name
📡 Supabase Realtime: đang kết nối...
✅ Supabase Realtime: Đang lắng nghe bảng cameras & camera_provisioning
🚀 [Violation] Đã lưu vi phạm mới | ID: 123 | Cam: 1 | Biển: 51H-123.45
☁️  Upload thành công | violations/vehicle_cam1_...jpg -> https://...
```
