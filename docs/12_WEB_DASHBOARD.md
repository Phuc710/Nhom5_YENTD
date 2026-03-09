# Web dashboard

Tài liệu này mô tả web hiện tại theo đúng hướng triển khai mới:

- web quản trị cho lực lượng cảnh sát và vận hành
- không chứa khu public cho người dân
- toàn bộ web hiện tại nằm trong `frontend/`

## 1. Cấu trúc web

### Khu quản trị

- [`frontend/index.php`](/c:/Users/Phucc/Desktop/ytd/frontend/index.php)
  Trung tâm điều phối

- [`frontend/cameras.php`](/c:/Users/Phucc/Desktop/ytd/frontend/cameras.php)
  Danh mục camera

- [`frontend/camera.php`](/c:/Users/Phucc/Desktop/ytd/frontend/camera.php)
  Chi tiết camera, stream, zone, setting

- [`frontend/violations.php`](/c:/Users/Phucc/Desktop/ytd/frontend/violations.php)
  Danh sách toàn bộ vi phạm

- [`frontend/violation-detail.php`](/c:/Users/Phucc/Desktop/ytd/frontend/violation-detail.php)
  Chi tiết một hồ sơ vi phạm

## 2. Chức năng web quản trị

### Trung tâm giám sát

- xem tổng quan toàn hệ thống
- xem số vi phạm hôm nay
- xem tổng camera online
- truy cập nhanh sang camera và vi phạm
- xem vi phạm gần nhất
- dữ liệu trang này lấy từ namespace `GET /api/dashboard/*`

### Quản lý camera

- danh sách toàn bộ camera
- tìm theo tên hoặc vị trí
- lọc online hoặc offline
- mở nhanh trang camera chi tiết

### Chi tiết camera

- xem stream trực tiếp
- xem stream URL
- xem IP, MAC, firmware, last seen
- sửa metadata camera
- trong hộp cấu hình camera chỉ có `1` nút điều khiển thiết bị trên web:
  `Factory reset thiết bị`
- xem vị trí trên Google Maps
- vẽ zone `detection`, `stop_line`, `roi`
- lưu zone qua API
- xem các vi phạm gần nhất của camera đó

Ghi chú:

- trạng thái đèn hiện thời vẫn đang đi qua ThingsBoard telemetry
- web chỉ có quyền gửi `factoryReset`
- ThingsBoard vẫn giữ toàn quyền RPC/attributes như bình thường
- web cảnh sát hiện tập trung vào camera, hồ sơ vi phạm, zone và trạng thái online của thiết bị

### Danh sách vi phạm

- lọc theo camera
- lọc theo biển số
- lọc theo ngày bắt đầu và ngày kết thúc
- xem từng hồ sơ

### Chi tiết vi phạm

- ảnh full frame
- ảnh crop biển số
- thông tin biển số
- thời gian vi phạm
- camera và vị trí
- trạng thái đèn
- confidence
- vote OCR
- chất lượng ảnh
- thời gian xử lý
- liên kết quay về camera tương ứng

## 3. Nền tảng OOP của frontend

Các file nền:

- [`frontend/bootstrap.php`](/c:/Users/Phucc/Desktop/ytd/frontend/bootstrap.php)
- [`frontend/app/Core/Page.php`](/c:/Users/Phucc/Desktop/ytd/frontend/app/Core/Page.php)
- [`frontend/app/Support/Nav.php`](/c:/Users/Phucc/Desktop/ytd/frontend/app/Support/Nav.php)

Mục tiêu:

- không để từng page PHP tự quản lý mọi thứ riêng lẻ
- gom config client, nav và layout vào một nền thống nhất

## 4. Lưu ý triển khai hosting

- file [`frontend/.htaccess`](/c:/Users/Phucc/Desktop/ytd/frontend/.htaccess) đã được thêm để chặn truy cập trực tiếp vào `app/`, `includes/`, `config.php`, `bootstrap.php`
- web dùng các file `.php` trực tiếp, phù hợp cho shared hosting Apache
- frontend chỉ cần cấu hình đúng `API_URL`
