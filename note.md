1. Lệnh chạy hệ thống
Chạy tất cả các dịch vụ (ThingsBoard, Mosquitto, Backend) ở chế độ chạy ngầm (detached mode):

powershell
docker compose up -d
Nếu bạn muốn xem log trực tiếp từ các container để kiểm tra lỗi, hãy bỏ -d:

powershell
docker compose up
2. Các lệnh hỗ trợ khác
Kiểm tra trạng thái các container:
powershell
docker compose ps
Dừng và xóa các container (nhưng vẫn giữ lại dữ liệu trong Volumes):
powershell
docker compose down
Xem log của một dịch vụ cụ thể (ví dụ: backend):
powershell
docker compose logs -f backend
Build lại backend (nếu bạn có thay đổi code trong thư mục /backend):
powershell
docker compose build backend
Lưu ý cho dự án của bạn:
ThingsBoard: Sẽ chạy tại địa chỉ http://localhost:9090.
Backend (FastAPI): Chạy tại http://localhost:8000.
Mosquitto (MQTT): Lắng nghe tại port 1888 trên máy host.
File này yêu cầu file .env tại đường dẫn ./backend/.env (hiện tại tôi thấy bạn đang mở file này, hãy đảm bảo các biến môi trường như DB host/pass đã đúng).


thingsboard healthy ở http://localhost:9090
mosquitto chạy ở localhost:1888
backend healthy ở http://localhost:8000/health


cd C:\Users\Phucc\Desktop\ytd
docker compose up -d

cd frontend
php -S localhost:8080 index.php -t .




  netsh advfirewall firewall show rule name=all | findstr :8000