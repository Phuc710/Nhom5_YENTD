"""
ProvisionServer — Lightweight HTTP server chạy trong QThread.
Nhận POST từ ESP32 tại /api/cameras/provision và đồng bộ vào Supabase.
Port: 8000 (giữ nguyên địa chỉ ESP32 đã cấu hình)
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ProvisionServer(QThread):
    """
    HTTP server gọn nhẹ — chỉ xử lý:
      POST /api/cameras/provision   ← ESP32 gửi lên
      GET  /health                  ← ESP32 check health (wifi_verify_url)
    Emit signal camera_provisioned(dict) khi nhận data hợp lệ.
    """

    camera_provisioned = pyqtSignal(dict)   # payload dict từ ESP32

    def __init__(self, host: str = "0.0.0.0", port: int = 8000, parent=None) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._on_provision: Optional[Callable[[dict], None]] = None

    # ── QThread entry ─────────────────────────────────────────────────────────

    def run(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # silence access log
                pass

            def do_GET(self):
                if self.path in ("/health", "/api/health"):
                    body = b'{"status":"ok","service":"traffic-monitor-qt"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/api/cameras/provision":
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        self.send_response(400)
                        self.end_headers()
                        return

                    # Xử lý provision + lưu DB
                    camera = outer._handle_provision(payload)

                    resp = json.dumps(camera).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(resp)))
                    self.end_headers()
                    self.wfile.write(resp)
                else:
                    self.send_response(404)
                    self.end_headers()

        try:
            self._server = HTTPServer((self._host, self._port), Handler)
            logger.info("ProvisionServer listening on %s:%d", self._host, self._port)
            self._server.serve_forever()
        except OSError as exc:
            logger.error("ProvisionServer failed to start: %s", exc)

    def stop(self) -> None:
        if self._server:
            threading.Thread(target=self._server.shutdown, daemon=True).start()

    # ── Core handler ──────────────────────────────────────────────────────────

    def _handle_provision(self, payload: dict) -> dict:
        """Lưu/cập nhật camera vào Supabase, trả về camera dict."""
        camera_id   = payload.get("camera_id", 1)
        mac         = payload.get("mac_address", "")
        ip          = payload.get("ip_address", "")
        stream_url  = payload.get("stream_url") or (f"http://{ip}:81/stream" if ip else "")
        device_name = payload.get("device_name") or payload.get("camera_name") or mac
        location    = payload.get("location", "Chưa xác định")

        logger.info(
            "[PROV] cam=%s mac=%s ip=%s name=%s",
            camera_id, mac, ip, device_name,
        )

        # Upsert camera vào Supabase qua CameraRepository
        result = self._upsert_camera(camera_id, payload, device_name, stream_url, location)
        # Thông báo lên UI thread
        self.camera_provisioned.emit(result)
        return result

    @staticmethod
    def _upsert_camera(
        camera_id: int,
        payload: dict,
        device_name: str,
        stream_url: str,
        location: str,
    ) -> dict:
        try:
            from backend.repositories.camera_repository import CameraRepository
            repo = CameraRepository()

            cam_payload = {
                "camera_id":   camera_id,
                "camera_name": device_name,
                "tb_device_name": device_name,
                "location":    location,
                "stream_url":  stream_url,
                "status":      "active",
            }
            if not repo.exists(camera_id):
                repo.create(cam_payload)
                logger.info("[PROV] Created new camera %s", camera_id)
            else:
                repo.update(camera_id, {
                    "camera_name": device_name,
                    "stream_url":  stream_url,
                    "location":    location,
                    "status":      "active",
                })
                logger.info("[PROV] Updated camera %s", camera_id)

            # Upsert provisioning record — CHỈ dùng các cột có trong bảng camera_provisioning
            # stream_url KHÔNG phải column của bảng này (nó thuộc bảng cameras)
            PROV_ALLOWED = {
                "camera_id", "mac_address", "ip_address",
                "device_name", "project_name", "device_model",
                "wifi_ssid", "access_token", "tb_device_name", "tb_device_id",
                "resolution", "fw_version", "idf_version",
                "stream_scheme", "stream_host", "stream_port",
                "stream_path", "stream_snapshot_path",
                "last_boot_at", "last_seen_at", "online",
            }
            prov = {k: v for k, v in payload.items() if k in PROV_ALLOWED}
            prov["camera_id"] = camera_id
            prov["online"]    = True
            repo.upsert_provisioning(prov)

            return {
                "camera_id":  camera_id,
                "camera_name": device_name,
                "stream_url": stream_url,
                "location":   location,
                "online":     True,
            }
        except Exception as exc:
            logger.error("[PROV] DB upsert failed: %s", exc)
            return {
                "camera_id":  camera_id,
                "stream_url": stream_url,
                "online":     True,
            }
