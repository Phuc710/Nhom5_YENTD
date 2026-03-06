# Hướng Dẫn Deploy Backend Lên VPS

## Yêu Cầu

- Ubuntu 20.04+ hoặc Debian 11+
- Python 3.9+
- RAM tối thiểu: 4GB (khuyến nghị 8GB)
- Storage: 20GB
- Public IP address

## Bước 1: Cập Nhật Hệ Thống

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git nginx -y
```

## Bước 2: Clone Project

```bash
cd /opt
sudo git clone YOUR_REPO_URL traffic-system
cd traffic-system/backend
```

## Bước 3: Setup Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Bước 4: Cấu Hình Environment

```bash
cp .env.example .env
nano .env
```

Sửa các giá trị:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

THINGSBOARD_URL=https://tcm-iot.imespro.ai
MQTT_HOST=103.249.117.212
MQTT_PORT=1883

DEBUG=False
LOG_LEVEL=INFO
```

## Bước 5: Test Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Mở browser: `http://YOUR_VPS_IP:8000/docs`

Nếu OK, Ctrl+C để dừng.

## Bước 6: Setup Systemd Service

Tạo file service:
```bash
sudo nano /etc/systemd/system/traffic-backend.service
```

Nội dung:
```ini
[Unit]
Description=Traffic Violation Detection Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/traffic-system/backend
Environment="PATH=/opt/traffic-system/backend/venv/bin"
ExecStart=/opt/traffic-system/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable và start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable traffic-backend
sudo systemctl start traffic-backend
sudo systemctl status traffic-backend
```

## Bước 7: Setup Nginx Reverse Proxy

Tạo config:
```bash
sudo nano /etc/nginx/sites-available/traffic-backend
```

Nội dung:
```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    client_max_body_size 20M;

    # API Backend
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # API Docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Static files (uploaded images)
    location /uploads {
        alias /opt/traffic-system/backend/uploads;
        autoindex off;
    }

    # Frontend
    location / {
        root /opt/traffic-system/frontend;
        index index.php index.html;
        try_files $uri $uri/ =404;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/traffic-backend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Bước 8: Setup Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

## Bước 9: Setup HTTPS (Khuyến nghị)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d YOUR_DOMAIN
```

Certbot tự động cấu hình HTTPS và auto-renew.

## Bước 10: Tạo Upload Directories

```bash
cd /opt/traffic-system/backend
mkdir -p uploads/original uploads/detected_plates
chmod 755 uploads
chmod 755 uploads/original
chmod 755 uploads/detected_plates
```

## Giám Sát & Logs

### Xem Logs Backend

```bash
# Real-time logs
sudo journalctl -u traffic-backend -f

# Last 100 lines
sudo journalctl -u traffic-backend -n 100

# Logs từ hôm nay
sudo journalctl -u traffic-backend --since today
```

### Xem Logs Nginx

```bash
# Access logs
sudo tail -f /var/log/nginx/access.log

# Error logs
sudo tail -f /var/log/nginx/error.log
```

### Kiểm Tra Status

```bash
sudo systemctl status traffic-backend
sudo systemctl status nginx
```

## Xử Lý Sự Cố

### Backend không start

```bash
# Xem logs chi tiết
sudo journalctl -u traffic-backend -n 50

# Kiểm tra port đã dùng chưa
sudo lsof -i :8000

# Restart service
sudo systemctl restart traffic-backend
```

### YOLO model không load

```bash
# Verify model files
ls -lh /opt/traffic-system/backend/ml/

# Kiểm tra permissions
chmod 644 /opt/traffic-system/backend/ml/*.pt
```

### RAM usage cao

```bash
# Kiểm tra memory
free -h

# Kiểm tra processes
htop

# Giảm workers trong systemd service
# Sửa --workers 4 thành --workers 2
sudo nano /etc/systemd/system/traffic-backend.service
sudo systemctl daemon-reload
sudo systemctl restart traffic-backend
```

## Bảo Trì

### Update Code

```bash
cd /opt/traffic-system
sudo git pull
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart traffic-backend
```

### Backup Database

Supabase tự động backup. Để manual backup:
```bash
# Export từ Supabase dashboard
# Hoặc dùng pg_dump nếu có direct access
```

### Dọn Dẹp Ảnh Cũ

```bash
# Xóa ảnh > 30 ngày
find /opt/traffic-system/backend/uploads -type f -mtime +30 -delete
```

## Tối Ưu Hiệu Năng

### 1. Dùng Gunicorn

```bash
pip install gunicorn

# Sửa ExecStart trong systemd service:
ExecStart=/opt/traffic-system/backend/venv/bin/gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 300
```

### 2. Enable Nginx Caching

Thêm vào nginx config:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=my_cache:10m max_size=1g inactive=60m;

location /uploads {
    proxy_cache my_cache;
    proxy_cache_valid 200 1h;
    alias /opt/traffic-system/backend/uploads;
}
```

### 3. Monitor Resources

```bash
# Cài monitoring tools
sudo apt install htop iotop nethogs -y
```

## Health Check

Backend có endpoint `/health`:

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-27T22:05:30.123456"
}
```

## Auto-Restart on Crash

Systemd đã cấu hình `Restart=always`, service tự restart khi crash.

## Production Checklist

- [ ] Đổi `DEBUG=False` trong `.env`
- [ ] Setup HTTPS với Certbot
- [ ] Cấu hình firewall
- [ ] Setup monitoring (Prometheus/Grafana)
- [ ] Backup strategy
- [ ] Log rotation
- [ ] Rate limiting
- [ ] Authentication cho dashboard
