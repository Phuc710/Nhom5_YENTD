# Mobile app và tra cứu người dùng

Hiện tại hướng ưu tiên của dự án là:

- web quản trị cho cảnh sát
- mobile cho người dân ở mức tài liệu thiết kế, chưa code

## 1. Phạm vi hiện tại

Trong giai đoạn này, luồng người dùng cuối được thực hiện bằng web responsive thay vì native mobile app riêng.

Lý do:

- triển khai nhanh hơn
- phù hợp hosting hiện tại
- dùng được ngay trên điện thoại
- không cần phát hành app store trong giai đoạn đầu

## 2. Vai trò mobile

Mobile là ứng dụng hoặc giao diện riêng cho người dân.

Mobile không phải web quản trị và không dùng chung với cục cảnh sát.

## 3. Quy tắc nghiệp vụ cho người dùng

- đăng nhập bằng biển số
- có biển số mới vào được khu tra cứu
- chỉ xem dữ liệu của biển số đang tra cứu
- không có quyền quản trị camera hoặc zone

## 4. Nếu làm native mobile sau này

Native app trong tương lai nên chỉ bao phủ:

- nhập biển số
- xem danh sách vi phạm của biển số đó
- xem chi tiết một vi phạm

Không nên đưa vào mobile user:

- config camera
- edit stream URL
- vẽ zone
- dashboard điều phối
- thao tác kỹ thuật cho thiết bị

## 5. API nên dùng cho mobile user

Ở trạng thái hiện tại, tài liệu mobile có thể tạm bám các API đọc sau:

- `GET /api/violations`
- `GET /api/violations/{id}`

Khi làm native mobile chuẩn hơn, nên có namespace user riêng hoặc API tra cứu biển số riêng để tránh phải lọc phía client.
