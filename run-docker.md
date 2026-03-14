# Hướng dẫn chạy Docker - Hệ thống YTD

Tài liệu này tổng hợp tất cả các lệnh cần thiết để vận hành hệ thống qua Docker.

## 🚀 1. Khởi động hệ thống

Chạy tất cả các dịch vụ (ThingsBoard, Mosquitto, Backend) ở chế độ chạy ngầm:
```powershell
docker compose up -d
```
*Lưu ý: ThingsBoard sẽ mất khoảng 2-5 phút để khởi động hoàn toàn UI.*

## 🛑 2. Dừng hệ thống

Dừng các container nhưng giữ nguyên dữ liệu:
```powershell
docker compose stop
```

Dừng và xóa các container (vẫn giữ dữ liệu trong Volumes):
```powershell
docker compose down
```

## 🧹 3. Reset hoàn toàn (Khi gặp lỗi ThingsBoard)

Nếu ThingsBoard bị lỗi loop install hoặc bạn muốn xóa sạch dữ liệu để chạy lại từ đầu:

1. Dừng hệ thống:
   ```powershell
   docker compose down
   ```
2. Xóa các volume dữ liệu:
   ```powershell
   docker volume rm ytd-tb-data ytd-tb-logs
   ```
3. Khởi động lại:
   ```powershell
   docker compose up -d
   ```

## 📋 4. Kiểm tra trạng thái và Log

Xem trạng thái các container:
```powershell
docker compose ps
```

Xem log trực tiếp của tất cả dịch vụ:
```powershell
docker compose logs -f
```

Xem log của một dịch vụ cụ thể (ví dụ: backend):
```powershell
docker compose logs -f backend
```

## 🛠️ 5. Cập nhật Code Backend

Nếu bạn thay đổi code trong thư mục `./backend`, hãy chạy lệnh này để build lại image:
```powershell
docker compose up -d --build backend
```

---

## 🔗 Thông tin truy cập

| Dịch vụ | URL | Tài khoản mặc định |
|---|---|---|
| **ThingsBoard UI** | [http://localhost:9090](http://localhost:9090) | `sysadmin@thingsboard.org` / `sysadmin` |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | - |
| **API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | - |
| **MQTT Broker** | `localhost:1888` | - |
