"""
Main Window — Cửa sổ chính của ứng dụng giám sát giao thông.
Sidebar navigation + stacked widget cho từng panel.
"""
from __future__ import annotations

import logging
import sys
from typing import List, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.core.mqtt_client import MqttClientThread
from app.core.provision_server import ProvisionServer
from app.ui.camera_panel import CameraPanel
from app.ui.violations_panel import ViolationsPanel
from app.ui.dashboard_panel import DashboardPanel

logger = logging.getLogger(__name__)


class FetchCamerasThread(QThread):
    done = pyqtSignal(list)

    def run(self) -> None:
        try:
            from backend.services.camera_service import CameraService
            cameras = CameraService().list_cameras()
            self.done.emit(cameras)
        except Exception as exc:
            logger.error("Fetch cameras failed: %s", exc)
            self.done.emit([])


# ─────────────────────────────────────────────────────────────────────────────


class Sidebar(QWidget):
    """Sidebar navigation với logo + nav buttons."""

    page_changed = pyqtSignal(int)

    _NAV_ITEMS = [
        ("📷", "Camera Live"),
        ("🚨", "Vi phạm"),
        ("📊", "Dashboard"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)
        self._btns: List[QPushButton] = []
        self._current = 0
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        logo_wrap = QWidget()
        logo_wrap.setObjectName("sidebar")
        logo_lay = QVBoxLayout(logo_wrap)
        logo_lay.setContentsMargins(16, 20, 16, 16)
        lbl_logo = QLabel("🚦 Traffic Monitor")
        lbl_logo.setObjectName("sidebar_logo")
        lbl_sub  = QLabel("Hệ thống giám sát\nvi phạm giao thông")
        lbl_sub.setObjectName("sidebar_sub")
        logo_lay.addWidget(lbl_logo)
        logo_lay.addWidget(lbl_sub)
        layout.addWidget(logo_wrap)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: #2d3748;")
        layout.addWidget(div)
        layout.addSpacing(8)

        # Nav buttons
        for idx, (icon, label) in enumerate(self._NAV_ITEMS):
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("nav_btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self._select(i))
            layout.addWidget(btn)
            self._btns.append(btn)

        layout.addStretch()

        # Status indicators
        self._lbl_mqtt  = self._status_dot("MQTT")
        self._lbl_stream = self._status_dot("Stream")
        layout.addWidget(self._lbl_mqtt)
        layout.addWidget(self._lbl_stream)
        layout.addSpacing(16)

        self._select(0)

    def _status_dot(self, label: str) -> QLabel:
        lbl = QLabel(f"⚫  {label}")
        lbl.setStyleSheet("color: #718096; font-size: 11px; padding: 4px 16px;")
        return lbl

    def _select(self, idx: int) -> None:
        for i, btn in enumerate(self._btns):
            btn.setChecked(i == idx)
        self._current = idx
        self.page_changed.emit(idx)

    def set_mqtt_status(self, connected: bool) -> None:
        icon  = "🟢" if connected else "🔴"
        color = "#68d391" if connected else "#fc8181"
        self._lbl_mqtt.setText(f"{icon}  MQTT")
        self._lbl_mqtt.setStyleSheet(f"color: {color}; font-size: 11px; padding: 4px 16px;")

    def set_stream_status(self, connected: bool) -> None:
        icon  = "🟢" if connected else "⚫"
        color = "#68d391" if connected else "#718096"
        self._lbl_stream.setText(f"{icon}  Stream")
        self._lbl_stream.setStyleSheet(f"color: {color}; font-size: 11px; padding: 4px 16px;")


# ─────────────────────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    """Cửa sổ chính của ứng dụng."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("🚦 Traffic Violation Monitor")
        self.setMinimumSize(1200, 720)
        self.resize(1400, 860)

        self._cameras: List[dict] = []
        self._mqtt_thread: Optional[MqttClientThread] = None
        self._provision_server: Optional[ProvisionServer] = None

        # Load cameras trước, rồi build UI
        self._fetch_cameras_and_init()

    def _fetch_cameras_and_init(self) -> None:
        self._fetch_thread = FetchCamerasThread(self)
        self._fetch_thread.done.connect(self._init_ui)
        self._fetch_thread.start()

    @pyqtSlot(list)
    def _init_ui(self, cameras: List[dict]) -> None:
        self._cameras = cameras

        # ── Central widget ─────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QHBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.page_changed.connect(self._on_page_changed)
        main_lay.addWidget(self._sidebar)

        # Content
        content = QWidget()
        content.setObjectName("content_area")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        self._stack = QStackedWidget()

        # Pages
        self._page_camera     = CameraPanel(cameras)
        self._page_violations = ViolationsPanel(cameras)
        self._page_dashboard  = DashboardPanel()

        # Wire traffic control signals
        self._page_camera.traffic_rpc_requested.connect(self._on_traffic_rpc)
        self._page_camera.traffic_timing_requested.connect(self._on_traffic_timing)
        # Wire violation realtime → ViolationsPanel (thay SSE) + Dashboard refresh
        self._page_camera.violation_occurred.connect(self._page_violations.on_new_violation)
        self._page_camera.violation_occurred.connect(self._page_dashboard.on_new_violation)

        self._stack.addWidget(self._page_camera)
        self._stack.addWidget(self._page_violations)
        self._stack.addWidget(self._page_dashboard)

        content_lay.addWidget(self._stack)
        main_lay.addWidget(content)

        # Status bar
        self._status = QStatusBar()
        self._status.showMessage("Đang khởi động...")
        self.setStatusBar(self._status)

        # Start MQTT
        self._start_mqtt()
        # Start Provision HTTP server (nhận ESP32 POST)
        self._start_provision_server()
        self._status.showMessage(f"Sẵn sàng | {len(cameras)} camera | HTTP:8000")

    def _on_page_changed(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)

    # ── MQTT ──────────────────────────────────────────────────────────────────

    def _start_mqtt(self) -> None:
        try:
            from backend.config.settings import get_settings
            s = get_settings()
            host = s.mqtt_host or "localhost"
            port = s.mqtt_port or 1888
        except Exception:
            host, port = "localhost", 1888

        self._mqtt_thread = MqttClientThread(host, port, parent=self)
        self._mqtt_thread.light_changed.connect(self._on_light_changed)
        self._mqtt_thread.traffic_status.connect(self._page_camera.on_traffic_status)
        self._mqtt_thread.connected.connect(lambda: self._sidebar.set_mqtt_status(True))
        self._mqtt_thread.disconnected.connect(lambda: self._sidebar.set_mqtt_status(False))
        # Wire light_state vào detection worker (nếu đang chạy)
        self._mqtt_thread.light_changed.connect(self._on_mqtt_light_for_detection)
        self._mqtt_thread.start()
        logger.info("MQTT thread started → %s:%d", host, port)

    # ── Provision server ──────────────────────────────────────────────────────

    def _start_provision_server(self) -> None:
        self._provision_server = ProvisionServer(host="0.0.0.0", port=8000, parent=self)
        self._provision_server.camera_provisioned.connect(self._on_camera_provisioned)
        self._provision_server.start()
        logger.info("Provision HTTP server started on port 8000")

    @pyqtSlot(dict)
    def _on_camera_provisioned(self, camera: dict) -> None:
        """ESP32 đã provision thành công — refresh camera list và auto-connect."""
        logger.info("[PROV] Camera provisioned: cam=%s url=%s",
                    camera.get('camera_id'), camera.get('stream_url'))
        # Reload cameras từ DB
        self._refresh_cameras_after_provision(camera)

    def _refresh_cameras_after_provision(self, new_cam: dict) -> None:
        """Reload camera list và update UI sau khi provision."""
        thread = FetchCamerasThread(self)
        thread.done.connect(lambda cams: self._apply_camera_refresh(cams, new_cam))
        thread.start()
        self._refresh_thread = thread  # giữ ref

    @pyqtSlot(list)
    def _apply_camera_refresh(self, cameras: List[dict], auto_cam: dict) -> None:
        self._cameras = cameras
        self._page_camera.refresh_cameras(cameras)
        self._page_violations.refresh_cameras(cameras)
        # Tìm và chọn camera vừa provision
        cam_id = auto_cam.get("camera_id")
        for i, cam in enumerate(cameras):
            if cam.get("camera_id") == cam_id:
                self._page_camera._cmb_camera.setCurrentIndex(i)
                break
        count = len(cameras)
        self._status.showMessage(
            f"Đã đồng bộ camera {cam_id} | Tổng: {count} camera | HTTP:8000"
        )

    @pyqtSlot(str, str)
    def _on_light_changed(self, device_name: str, state: str) -> None:
        self._page_camera.on_light_changed(device_name, state)

    @pyqtSlot(str, str)
    def _on_mqtt_light_for_detection(self, device_name: str, state: str) -> None:
        """Forward light_state từ MQTT → DetectionWorker (state machine xanh/đỏ)."""
        worker = getattr(self._page_camera, "_detect_worker", None)
        if worker is not None:
            worker.on_light_changed(device_name, state)

    @pyqtSlot(str, str)
    def _on_traffic_rpc(self, device_name: str, method: str) -> None:
        if self._mqtt_thread:
            self._mqtt_thread.send_traffic_rpc(device_name, method)
        logger.info("Traffic RPC: %s → %s", device_name, method)

    @pyqtSlot(str, int, int, int)
    def _on_traffic_timing(self, device_name: str, r: int, y: int, g: int) -> None:
        if self._mqtt_thread:
            self._mqtt_thread.send_traffic_timing(device_name, r, y, g)
        logger.info("Traffic timing: %s R=%d Y=%d G=%d", device_name, r, y, g)

    def closeEvent(self, event) -> None:
        if self._mqtt_thread:
            self._mqtt_thread.stop()
            self._mqtt_thread.wait(2000)
        if self._provision_server:
            self._provision_server.stop()
            self._provision_server.wait(1000)
        super().closeEvent(event)
