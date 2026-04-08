"""
Camera Panel — MJPEG stream + Zone Editor kiểu kéo 4 điểm (như OpenCV test.py).
Zone Editor: 4 điểm draggable polygon trên video live feed.
Traffic control: Python làm chủ → gửi MQTT → ESP32 thực thi.
"""
from __future__ import annotations

from typing import List, Optional
import time
import numpy as np

from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QPixmap,
    QPolygon, QPolygonF, QBrush, QPainterPath,
)
from PyQt5.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from app.core.stream_client import StreamClientThread
from app.core.detection_worker import DetectionWorker
from app.core import settings_store


# ─────────────────────────────────────────────────────────────────────────────
# Traffic Light Indicator
# ─────────────────────────────────────────────────────────────────────────────

class TrafficLightWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = "UNKNOWN"
        self._mode  = "normal"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)
        self._d_r = self._dot("#741c1c")
        self._d_y = self._dot("#6b5c10")
        self._d_g = self._dot("#1c4731")
        self._lbl = QLabel("―")
        self._lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._mode_lbl = QLabel("")
        self._mode_lbl.setStyleSheet("color:#f6e05e;font-size:10px;padding-left:6px;")
        for w in (self._d_r, self._d_y, self._d_g, self._lbl, self._mode_lbl):
            lay.addWidget(w)
        lay.addStretch()

    def _dot(self, color: str) -> QLabel:
        w = QLabel(); w.setFixedSize(26, 26)
        w.setStyleSheet(f"background:{color};border-radius:13px;")
        return w

    def set_state(self, state: str) -> None:
        self._state = state.upper()
        C = {
            "RED":    ("#fc5151","#6b5c10","#1c4731","#fc5151"),
            "YELLOW": ("#741c1c","#f6e05e","#1c4731","#f6e05e"),
            "GREEN":  ("#741c1c","#6b5c10","#48bb78","#68d391"),
        }
        rd, yl, gn, txt = C.get(self._state, ("#444","#444","#444","#a0aec0"))
        self._d_r.setStyleSheet(f"background:{rd};border-radius:13px;")
        self._d_y.setStyleSheet(f"background:{yl};border-radius:13px;")
        self._d_g.setStyleSheet(f"background:{gn};border-radius:13px;")
        self._lbl.setStyleSheet(f"color:{txt};font-weight:bold;background:transparent;")
        self._lbl.setText(self._state)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        labels = {"normal":"⚡ Tự động","emergency_red":"🚨 KHẨN CẤP ĐỎ","emergency_green":"🚦 KHẨN CẤP XANH"}
        self._mode_lbl.setText(labels.get(mode, ""))

    def set_remain(self, sec: int) -> None:
        if sec > 0 and self._mode == "normal":
            self._lbl.setText(f"{self._state}  {sec}s")


# ─────────────────────────────────────────────────────────────────────────────
# Stream View — kéo 4 điểm như OpenCV test.py
# ─────────────────────────────────────────────────────────────────────────────

POINT_RADIUS  = 9
LINE_COLOR_SL = QColor("#fc5151")   # stop line  — đỏ
FILL_COLOR_SL = QColor(252, 81, 81, 50)
LINE_COLOR_DZ = QColor("#48bb78")   # detect zone — xanh lá
FILL_COLOR_DZ = QColor(72, 187, 120, 50)
PT_NORMAL     = QColor("#fc5151")
PT_SELECTED   = QColor("#ffd700")   # vàng khi đang kéo


class StreamView(QLabel):
    """MJPEG view + 4-point draggable zone editor (stop line + detect zone)."""

    zone_updated  = pyqtSignal(dict)   # {stop_line, detect_zone, frame_w, frame_h}
    frame_counted = pyqtSignal()       # mỗi frame mới → FPS counter

    MODE_IDLE = 0
    MODE_EDIT_SL  = 1   # edit stop line (2 pts)
    MODE_EDIT_DZ  = 2   # edit detect zone (4 pts)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)

        self._mode     = self.MODE_IDLE
        self._drag_idx = -1   # index of point being dragged

        # Stop line: 2 điểm normalized
        self._sl_pts: Optional[List[QPointF]] = None   # [p0, p1]
        # Detect zone: 4 điểm normalized
        self._dz_pts: Optional[List[QPointF]] = None   # [p0,p1,p2,p3]

        self._orig_w = 640
        self._orig_h = 480
        self._last_pixmap: Optional[QPixmap] = None
        self._detections: list = []

        self._set_border(False)
        self.setText("📷  Chưa kết nối stream")

    def _set_border(self, ok: bool) -> None:
        c = "#48bb78" if ok else "#fc8181"
        self.setStyleSheet(
            f"background:#050710;border:2px solid {c};border-radius:8px;"
            "color:#718096;font-size:16px;"
        )

    # ── Zone editor API ────────────────────────────────────────────────────────

    def start_edit_stop_line(self) -> None:
        """Đặt 2 điểm mặc định rồi vào chế độ kéo stop line."""
        if self._sl_pts is None:
            # Mặc định: ngang 1/3 dưới frame
            y = 0.7
            self._sl_pts = [QPointF(0.15, y), QPointF(0.85, y)]
        self._mode     = self.MODE_EDIT_SL
        self._drag_idx = -1
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    def start_edit_detect_zone(self) -> None:
        """Đặt 4 điểm mặc định rồi vào chế độ kéo detect zone."""
        if self._dz_pts is None:
            self._dz_pts = [
                QPointF(0.15, 0.2),  # top-left
                QPointF(0.85, 0.2),  # top-right
                QPointF(0.85, 0.65), # bottom-right
                QPointF(0.15, 0.65), # bottom-left
            ]
        self._mode     = self.MODE_EDIT_DZ
        self._drag_idx = -1
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    def stop_edit(self) -> None:
        """Lưu và thoát edit mode."""
        self._mode     = self.MODE_IDLE
        self._drag_idx = -1
        self.setCursor(Qt.ArrowCursor)
        self._emit_zones()
        self.update()

    def clear_zones(self) -> None:
        self._sl_pts   = None
        self._dz_pts   = None
        self._mode     = self.MODE_IDLE
        self._drag_idx = -1
        self.setCursor(Qt.ArrowCursor)
        self.zone_updated.emit({"stop_line": None, "detect_zone": None})
        self.update()

    def get_zones_np(self) -> dict:
        """Trả về zones dưới dạng numpy array (normalized 0..1)."""
        sl = None
        if self._sl_pts and len(self._sl_pts) == 2:
            sl = np.array([[p.x(), p.y()] for p in self._sl_pts], dtype=np.float32)
        dz = None
        if self._dz_pts and len(self._dz_pts) == 4:
            dz = np.array([[p.x(), p.y()] for p in self._dz_pts], dtype=np.float32)
        return {"stop_line": sl, "detect_zone": dz, "frame_w": self._orig_w, "frame_h": self._orig_h}

    def _emit_zones(self) -> None:
        self.zone_updated.emit(self.get_zones_np())

    # ── Mouse events ──────────────────────────────────────────────────────────

    def _active_pts(self) -> Optional[List[QPointF]]:
        if self._mode == self.MODE_EDIT_SL:
            return self._sl_pts
        if self._mode == self.MODE_EDIT_DZ:
            return self._dz_pts
        return None

    def _find_nearest(self, pos: QPoint) -> int:
        pts = self._active_pts()
        if not pts:
            return -1
        ox, oy, vw, vh = self._video_rect()
        threshold_sq = (POINT_RADIUS + 8) ** 2
        best_i, best_d = -1, threshold_sq + 1
        for i, p in enumerate(pts):
            sx = ox + p.x() * vw
            sy = oy + p.y() * vh
            d  = (sx - pos.x()) ** 2 + (sy - pos.y()) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        return best_i if best_d <= threshold_sq else -1

    def _screen_to_norm(self, pos: QPoint) -> QPointF:
        ox, oy, vw, vh = self._video_rect()
        nx = max(0.0, min(1.0, (pos.x() - ox) / max(vw, 1)))
        ny = max(0.0, min(1.0, (pos.y() - oy) / max(vh, 1)))
        return QPointF(nx, ny)

    def mousePressEvent(self, ev) -> None:
        if self._mode != self.MODE_IDLE and ev.button() == Qt.LeftButton:
            self._drag_idx = self._find_nearest(ev.pos())
            if self._drag_idx >= 0:
                self.setCursor(Qt.ClosedHandCursor)
            self.update()
        else:
            super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._mode != self.MODE_IDLE and self._drag_idx >= 0:
            pts = self._active_pts()
            if pts:
                pts[self._drag_idx] = self._screen_to_norm(ev.pos())
                self.update()
        elif self._mode != self.MODE_IDLE:
            # Hover highlight
            idx = self._find_nearest(ev.pos())
            self.setCursor(Qt.OpenHandCursor if idx >= 0 else Qt.CrossCursor)
        else:
            super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if self._mode != self.MODE_IDLE and ev.button() == Qt.LeftButton:
            self._drag_idx = -1
            self.setCursor(Qt.OpenHandCursor)
            self._emit_zones()
        else:
            super().mouseReleaseEvent(ev)

    # ── Video rect ─────────────────────────────────────────────────────────────

    def _video_rect(self):
        pw, ph = self.width(), self.height()
        ow, oh = self._orig_w, self._orig_h
        scale  = min(pw / max(ow, 1), ph / max(oh, 1))
        vw, vh = ow * scale, oh * scale
        ox, oy = (pw - vw) / 2, (ph - vh) / 2
        return ox, oy, vw, vh

    # ── Frame update ───────────────────────────────────────────────────────────

    @pyqtSlot(QImage, np.ndarray)
    def update_frame(self, qt_img: QImage, _frame: np.ndarray) -> None:
        self.setText("")
        self._orig_w = max(qt_img.width(), 1)
        self._orig_h = max(qt_img.height(), 1)
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._last_pixmap = pixmap
        self._redraw()
        self.frame_counted.emit()   # ← đếm FPS stream

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._mode != self.MODE_IDLE:
            self._paint_zones_overlay()

    def _redraw(self) -> None:
        if self._last_pixmap is None:
            return
        pm = self._last_pixmap.copy()
        p  = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # Pixmap đã scaled, origin luôn (0,0), size = pm.width()/pm.height()
        # KHÔNG dùng _video_rect() (widget-space) khi paint trên pixmap!
        pw, ph = float(pm.width()), float(pm.height())
        self._draw_detections(p, 0.0, 0.0, pw, ph)
        if self._mode == self.MODE_IDLE:
            self._draw_zone_on_pixmap(p, 0.0, 0.0, pw, ph)
        p.end()
        self.setPixmap(pm)

    def _paint_zones_overlay(self) -> None:
        """Paint overlay khi đang edit (trên Widget, không phải pixmap)."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        ox, oy, vw, vh = self._video_rect()
        self._draw_zone_on_pixmap(p, ox, oy, vw, vh)
        p.end()

    def _draw_zone_on_pixmap(self, p: QPainter, ox, oy, vw, vh) -> None:
        def to_screen(npt: QPointF):
            return QPoint(int(ox + npt.x() * vw), int(oy + npt.y() * vh))

        # ─ Stop line ─────────────────────────────────────────────────────────
        if self._sl_pts and len(self._sl_pts) == 2:
            pts_s = [to_screen(p_) for p_ in self._sl_pts]
            pen   = QPen(LINE_COLOR_SL, 3)
            p.setPen(pen)
            p.drawLine(pts_s[0], pts_s[1])
            # Label
            mid = (pts_s[0] + pts_s[1]) / 2
            mid_pt = QPoint(int((pts_s[0].x() + pts_s[1].x()) / 2),
                            int((pts_s[0].y() + pts_s[1].y()) / 2))
            lbl_w = 78
            p.fillRect(mid_pt.x() - lbl_w//2, mid_pt.y() - 22, lbl_w, 20,
                       QColor(252, 81, 81, 190))
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(mid_pt.x() - lbl_w//2 + 4, mid_pt.y() - 6, "STOP LINE")
            # Points
            for i, spt in enumerate(pts_s):
                is_sel = (self._mode == self.MODE_EDIT_SL and i == self._drag_idx)
                col = PT_SELECTED if is_sel else QColor("#fc5151")
                p.setBrush(QBrush(col))
                p.setPen(QPen(QColor("white"), 2))
                p.drawEllipse(spt, POINT_RADIUS, POINT_RADIUS)
                p.setPen(QColor("white"))
                p.setFont(QFont("Segoe UI", 8, QFont.Bold))
                p.drawText(spt.x() + 12, spt.y() - 6, f"P{i+1}")

        # ─ Detect zone ───────────────────────────────────────────────────────
        if self._dz_pts and len(self._dz_pts) == 4:
            pts_s = [to_screen(p_) for p_ in self._dz_pts]
            poly   = QPolygon(pts_s)
            # Fill — QPainterPath.addPolygon() yêu cầu QPolygonF, không nhận QPolygon
            poly_f = QPolygonF(pts_s)
            path   = QPainterPath()
            path.addPolygon(poly_f)
            p.fillPath(path, QBrush(FILL_COLOR_DZ))
            # Border
            p.setPen(QPen(LINE_COLOR_DZ, 2))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(poly)
            # Label
            cx = int(sum(pt.x() for pt in pts_s) / 4)
            cy = int(sum(pt.y() for pt in pts_s) / 4)
            lbl_w = 100
            p.fillRect(cx - lbl_w//2, cy - 14, lbl_w, 20, QColor(72, 187, 120, 190))
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(cx - lbl_w//2 + 4, cy + 2, "DETECT ZONE")
            # Corner points
            for i, spt in enumerate(pts_s):
                is_sel = (self._mode == self.MODE_EDIT_DZ and i == self._drag_idx)
                col = PT_SELECTED if is_sel else QColor("#48bb78")
                p.setBrush(QBrush(col))
                p.setPen(QPen(QColor("white"), 2))
                p.drawEllipse(spt, POINT_RADIUS, POINT_RADIUS)
                p.setPen(QColor("white"))
                p.setFont(QFont("Segoe UI", 8, QFont.Bold))
                px_  = spt.x() + 12
                py_  = spt.y() - 6
                corner = ["TL","TR","BR","BL"][i]
                p.drawText(px_, py_, f"P{i+1}({corner})")

    def _draw_detections(self, p: QPainter, ox, oy, vw, vh) -> None:
        if not self._detections:
            return
        for det in self._detections:
            bbox  = det.get("bbox") or {}
            # bbox values are PIXEL coords from detector's preprocessed frame
            # → normalize to 0..1 using frame dimensions, then map to screen
            raw_x1 = bbox.get("x1", 0)
            raw_y1 = bbox.get("y1", 0)
            raw_x2 = bbox.get("x2", 0)
            raw_y2 = bbox.get("y2", 0)

            ow = max(self._orig_w, 1)
            oh = max(self._orig_h, 1)
            x1 = int(ox + (raw_x1 / ow) * vw)
            y1 = int(oy + (raw_y1 / oh) * vh)
            x2 = int(ox + (raw_x2 / ow) * vw)
            y2 = int(oy + (raw_y2 / oh) * vh)

            is_vio = det.get("is_violation", False)
            plate  = det.get("plate_text") or ""
            conf   = det.get("confidence", 0.0)

            # Box color: red for violation, cyan for normal detect
            color = QColor("#fc5151") if is_vio else QColor("#00e5ff")
            p.setPen(QPen(color, 3))
            p.setBrush(Qt.NoBrush)
            p.drawRect(x1, y1, x2 - x1, y2 - y1)

            # Confidence badge (top-right of box)
            conf_text = f"{conf*100:.0f}%"
            p.setFont(QFont("Consolas", 8, QFont.Bold))
            fm = p.fontMetrics()
            cw = fm.horizontalAdvance(conf_text) + 8
            ch = fm.height() + 4
            p.fillRect(x2 - cw, y1, cw, ch, QColor(0, 0, 0, 180))
            p.setPen(QColor("#f6e05e"))
            p.drawText(x2 - cw + 4, y1 + fm.ascent() + 2, conf_text)

            # Plate text badge (below box)
            if plate:
                p.setFont(QFont("Consolas", 11, QFont.Bold))
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(plate) + 16
                th = fm.height() + 8
                badge_x = x1
                badge_y = y2 + 2
                # Background pill
                bg_color = QColor("#fc5151") if is_vio else QColor("#00c853")
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(bg_color))
                p.drawRoundedRect(badge_x, badge_y, tw, th, 4, 4)
                # Text
                p.setPen(QColor("white"))
                p.drawText(badge_x + 8, badge_y + fm.ascent() + 4, plate)

    def set_detections(self, detections: list) -> None:
        self._detections = detections
        self._redraw()   # re-draw ngay để bbox hiện lên màn hình

    def set_connected(self, connected: bool) -> None:
        self._set_border(connected)
        if not connected:
            self._last_pixmap = None
            self.setText("📷  Chưa kết nối stream")


# ─────────────────────────────────────────────────────────────────────────────
# Camera Panel
# ─────────────────────────────────────────────────────────────────────────────

class CameraPanel(QWidget):
    """Panel camera chính: stream + traffic control + zone editor."""

    traffic_rpc_requested    = pyqtSignal(str, str)
    traffic_timing_requested = pyqtSignal(str, int, int, int)
    violation_occurred       = pyqtSignal(dict)   # vi phạm mới → ViolationsPanel
    pcb_ping_requested       = pyqtSignal(str, str)  # (device_name, method) — gửi getStatus

    def __init__(self, cameras: list, parent=None) -> None:
        super().__init__(parent)
        self._cameras        = cameras
        self._current_cam: Optional[dict] = None
        self._current_device = ""        # camera device name (cho stream/telemetry)
        self._pcb_device     = "pcb-tl-01" # PCB device name (phải khớp với DEVICE_NAME trong firmware)
        self._stream_thread: Optional[StreamClientThread] = None
        self._detect_worker: Optional[DetectionWorker]    = None
        self._frame_count    = 0
        self._ai_fps         = 0.0
        self._zone_editing   = False
        self._last_rpc_time  = 0.0
        self._video_file_path: str = ""   # đường dẫn file video local (rỗng = dùng camera)

        self._pcb_connected: bool = False  # trạng thái kết nối PCB

        # Timer tự cượng offline nếu không nhận được telemetry trong 4s
        self._pcb_timeout_timer = QTimer(self)
        self._pcb_timeout_timer.setSingleShot(True)
        self._pcb_timeout_timer.timeout.connect(self._on_pcb_timeout)

        self._build_ui()
        self._populate_cameras()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("📷  Live Camera")
        title.setObjectName("page_title")
        hdr.addWidget(title)
        hdr.addStretch()

        # PCB Status indicator in header
        self._lbl_pcb_header = QLabel("PCB: ⚫ Offline")
        self._lbl_pcb_header.setStyleSheet("color: #718096; font-size: 12px; font-weight: bold; margin-right: 15px;")
        hdr.addWidget(self._lbl_pcb_header)

        self._cmb_camera = QComboBox()
        self._cmb_camera.setMinimumWidth(220)
        hdr.addWidget(self._cmb_camera)
        self._btn_connect = QPushButton("🔌  Kết nối")
        self._btn_connect.setObjectName("btn_success")
        self._btn_connect.setFixedHeight(36)
        self._btn_connect.setMinimumWidth(130)
        self._btn_connect.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._btn_connect.clicked.connect(self._on_connect_toggle)
        hdr.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("⏹  Ngắt kết nối")
        self._btn_disconnect.setObjectName("btn_danger")
        self._btn_disconnect.setFixedHeight(36)
        self._btn_disconnect.setMinimumWidth(130)
        self._btn_disconnect.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._btn_disconnect.clicked.connect(self._stop_stream)
        self._btn_disconnect.hide()
        hdr.addWidget(self._btn_disconnect)

        root.addLayout(hdr)

        # ── Source selector ─────────────────────────────────────────────────
        src_row = QHBoxLayout()
        lbl_src = QLabel("Nguồn:")
        lbl_src.setStyleSheet("color:#718096;font-size:11px;")
        src_row.addWidget(lbl_src)

        self._cmb_source = QComboBox()
        self._cmb_source.setMinimumWidth(160)
        self._cmb_source.addItem("📡  Camera (DB)", "db")
        self._cmb_source.addItem("🎞  File video...", "file")
        self._cmb_source.addItem("📷  Webcam", "webcam")
        self._cmb_source.currentIndexChanged.connect(self._on_source_changed)
        src_row.addWidget(self._cmb_source)

        self._btn_browse = QPushButton("📂 Mở file")
        self._btn_browse.setFixedHeight(32)
        self._btn_browse.setMinimumWidth(100)
        self._btn_browse.setEnabled(False)
        self._btn_browse.clicked.connect(self._on_browse_video)
        src_row.addWidget(self._btn_browse)

        self._lbl_file = QLabel("(chưa chọn)")
        self._lbl_file.setStyleSheet("color:#718096;font-size:10px;")
        self._lbl_file.setVisible(False)
        src_row.addWidget(self._lbl_file, 1)
        src_row.addStretch()

        root.addLayout(src_row)

        # Body
        body = QHBoxLayout()
        body.setSpacing(12)

        # Stream view
        self._sv = StreamView()
        self._sv.zone_updated.connect(self._on_zone_updated)
        self._sv.frame_counted.connect(self._on_frame_counted)  # FPS stream
        body.addWidget(self._sv, stretch=3)

        # Right panel
        right = QVBoxLayout()
        right.setSpacing(10)

        # ── Traffic light ──────────────────────────────────────────────────
        tl_grp = QGroupBox("🚦 Đèn giao thông (ESP32_PCB)")
        tl_lay = QVBoxLayout(tl_grp)

        # PCB device name row
        from PyQt5.QtWidgets import QLineEdit
        pcb_row = QHBoxLayout()
        pcb_lbl = QLabel("PCB Device:")
        pcb_lbl.setStyleSheet("color:#718096;font-size:10px;")
        pcb_lbl.setFixedWidth(72)
        self._pcb_input = QLineEdit(self._pcb_device)
        self._pcb_input.setPlaceholderText("pcb-tl-01")
        self._pcb_input.setFixedHeight(26)
        self._pcb_input.setStyleSheet(
            "background:#2d3748;color:#e2e8f0;border:1px solid #4a5568;"
            "border-radius:4px;padding:2px 6px;font-size:11px;"
        )
        self._pcb_input.textChanged.connect(self._on_pcb_device_changed)
        self._pcb_status_dot = QLabel("⚫")
        self._pcb_status_dot.setFixedWidth(20)
        pcb_row.addWidget(pcb_lbl)
        pcb_row.addWidget(self._pcb_input, 1)
        pcb_row.addWidget(self._pcb_status_dot)
        tl_lay.addLayout(pcb_row)

        # PCB Connect / Disconnect buttons
        pcb_btn_row = QHBoxLayout()
        self._btn_pcb_connect = QPushButton("🔌  Kết nối PCB")
        self._btn_pcb_connect.setObjectName("btn_success")
        self._btn_pcb_connect.setFixedHeight(30)
        self._btn_pcb_connect.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn_pcb_connect.clicked.connect(self._on_pcb_connect)
        pcb_btn_row.addWidget(self._btn_pcb_connect)

        self._btn_pcb_disconnect = QPushButton("⏹  Ngắt PCB")
        self._btn_pcb_disconnect.setObjectName("btn_danger")
        self._btn_pcb_disconnect.setFixedHeight(30)
        self._btn_pcb_disconnect.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn_pcb_disconnect.clicked.connect(self._on_pcb_disconnect)
        self._btn_pcb_disconnect.hide()
        pcb_btn_row.addWidget(self._btn_pcb_disconnect)
        tl_lay.addLayout(pcb_btn_row)

        self._tl = TrafficLightWidget()
        tl_lay.addWidget(self._tl)

        row1 = QHBoxLayout()
        self._btn_normal = QPushButton("⚡ Tự động")
        self._btn_normal.setObjectName("btn_primary")
        self._btn_normal.clicked.connect(lambda: self._send_rpc("setNormalMode"))
        self._btn_normal.setEnabled(False)  # bị khóa cho đến khi kết nối PCB
        row1.addWidget(self._btn_normal)
        tl_lay.addLayout(row1)

        row2 = QHBoxLayout()
        self._btn_er = QPushButton("🔴 Khẩn cấp ĐỎ")
        self._btn_er.setObjectName("btn_danger")
        self._btn_er.setToolTip("Giữ đèn ĐỎ — dừng tất cả (xe khẩn cấp ngang qua)")
        self._btn_er.clicked.connect(lambda: self._send_rpc("setEmergencyRed"))
        self._btn_er.setEnabled(False)
        row2.addWidget(self._btn_er)
        self._btn_eg = QPushButton("🟢 Khẩn cấp XANH")
        self._btn_eg.setObjectName("btn_success")
        self._btn_eg.setToolTip("Giữ đèn XANH — thông đường (xe khẩn cấp qua luồng này)")
        self._btn_eg.clicked.connect(lambda: self._send_rpc("setEmergencyGreen"))
        self._btn_eg.setEnabled(False)
        row2.addWidget(self._btn_eg)
        tl_lay.addLayout(row2)

        # Timing
        timing = QGroupBox("⏱ Pha (giây)")
        t_lay  = QHBoxLayout(timing)
        for lbl, attr, val in [("🔴","_sr",5),("🟡","_sy",2),("🟢","_sg",7)]:
            t_lay.addWidget(QLabel(lbl))
            sp = QSpinBox(); sp.setRange(1, 300); sp.setSuffix("s"); sp.setValue(val)
            setattr(self, attr, sp); t_lay.addWidget(sp)
        self._btn_timing = QPushButton("Áp dụng")
        self._btn_timing.setObjectName("btn_primary")
        self._btn_timing.clicked.connect(self._send_timing)
        self._btn_timing.setEnabled(False)
        t_lay.addWidget(self._btn_timing)
        tl_lay.addWidget(timing)
        right.addWidget(tl_grp)

        # ── Zone editor ────────────────────────────────────────────────────
        z_grp = QGroupBox("🗺 Zone Editor")
        z_lay = QVBoxLayout(z_grp)
        z_tip = QLabel("Kéo thả 4 điểm để điều chỉnh vùng")
        z_tip.setStyleSheet("color:#718096;font-size:10px;")
        z_lay.addWidget(z_tip)
        z_row = QHBoxLayout()

        self._btn_edit_sl = QPushButton("📏 Stop Line")
        self._btn_edit_sl.setObjectName("btn_primary")
        self._btn_edit_sl.clicked.connect(self._toggle_edit_sl)
        z_row.addWidget(self._btn_edit_sl)

        self._btn_edit_dz = QPushButton("🔷 Detect Zone")
        self._btn_edit_dz.setObjectName("btn_primary")
        self._btn_edit_dz.clicked.connect(self._toggle_edit_dz)
        z_row.addWidget(self._btn_edit_dz)

        self._btn_save_zone = QPushButton("💾 Lưu")
        self._btn_save_zone.setObjectName("btn_success")
        self._btn_save_zone.clicked.connect(self._save_zones)
        z_row.addWidget(self._btn_save_zone)

        self._btn_clear_zone = QPushButton("🗑 Xóa")
        self._btn_clear_zone.setObjectName("btn_danger")
        self._btn_clear_zone.clicked.connect(self._sv.clear_zones)
        z_row.addWidget(self._btn_clear_zone)
        z_lay.addLayout(z_row)

        self._lbl_zone = QLabel("Chưa có zone")
        self._lbl_zone.setStyleSheet("color:#718096;font-size:10px;")
        self._lbl_zone.setWordWrap(True)
        z_lay.addWidget(self._lbl_zone)
        right.addWidget(z_grp)

        # ── Camera info ────────────────────────────────────────────────────
        info_grp = QGroupBox("Thông tin")
        i_lay = QVBoxLayout(info_grp)
        self._lbl_ip     = self._row(i_lay, "IP:")
        self._lbl_mac    = self._row(i_lay, "MAC:")
        self._lbl_url    = self._row(i_lay, "Stream:")
        self._lbl_status = self._row(i_lay, "Trạng thái:")
        self._lbl_fps    = self._row(i_lay, "FPS Stream:")
        self._lbl_ai_fps = self._row(i_lay, "FPS AI:")
        right.addWidget(info_grp)
        right.addStretch()

        body.addLayout(right, stretch=1)
        root.addLayout(body)

        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._tick_fps)
        self._fps_timer.start(1000)

    def _row(self, layout, lbl: str) -> QLabel:
        row = QHBoxLayout()
        k = QLabel(lbl); k.setFixedWidth(72)
        k.setStyleSheet("color:#718096;font-size:11px;")
        v = QLabel("―"); v.setStyleSheet("color:#e2e8f0;font-size:12px;")
        v.setWordWrap(True)
        row.addWidget(k); row.addWidget(v, 1)
        layout.addLayout(row)
        return v

    # ── Camera management ─────────────────────────────────────────────────────

    def _populate_cameras(self) -> None:
        self._cmb_camera.blockSignals(True)
        self._cmb_camera.clear()
        for cam in self._cameras:
            name = cam.get("camera_name") or cam.get("tb_device_name") or f"Cam {cam.get('camera_id')}"
            self._cmb_camera.addItem(name, cam)
        self._cmb_camera.blockSignals(False)
        if self._cameras:
            self._cmb_camera.setCurrentIndex(0)
            self._load_cam(self._cameras[0])

    def refresh_cameras(self, cameras: list) -> None:
        old_id = self._current_cam.get("camera_id") if self._current_cam else None
        self._cameras = cameras
        self._populate_cameras()
        if old_id:
            for i in range(self._cmb_camera.count()):
                d = self._cmb_camera.itemData(i)
                if d and d.get("camera_id") == old_id:
                    self._cmb_camera.setCurrentIndex(i)
                    break

    def _load_cam(self, cam: dict) -> None:
        self._current_cam    = cam
        self._current_device = cam.get("tb_device_name") or cam.get("camera_name") or ""
        self._lbl_ip.setText(cam.get("ip_address") or "―")
        self._lbl_mac.setText(cam.get("mac_address") or "―")
        self._lbl_url.setText(cam.get("stream_url") or "Chưa có URL")
        self._lbl_status.setText("Chưa kết nối")
        self._load_saved_settings(cam.get("camera_id", 0))

    def _on_connect_toggle(self) -> None:
        cam_data = self._cmb_camera.currentData()
        if cam_data:
            self._load_cam(cam_data)
        self._start_stream()

    def _on_source_changed(self, index: int) -> None:
        """Khi user chọn nguồn khác — hiện/ẩn nút Browse."""
        src = self._cmb_source.currentData()
        is_file = (src == "file")
        self._btn_browse.setEnabled(is_file)
        self._lbl_file.setVisible(is_file)
        # Nếu chuyển về camera DB → tắt hiển thị file
        if not is_file:
            self._video_file_path = ""

    def _on_browse_video(self) -> None:
        """Mở file dialog để chọn file video."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file video",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.m4v *.ts);;All Files (*)",
        )
        if path:
            self._video_file_path = path
            # Hiển thị tên file ngắn gọn
            import os
            self._lbl_file.setText(os.path.basename(path))
            self._lbl_file.setStyleSheet("color:#68d391;font-size:10px;")  # xanh lá

    # ── Stream ─────────────────────────────────────────────────────────────────

    def _start_stream(self) -> None:
        if not self._current_cam:
            return
        url = self._current_cam.get("stream_url") or ""
        if not url:
            self._lbl_status.setText("❌ Không có URL"); return
        cam_id = self._current_cam.get("camera_id", 0)

        # ── [SOURCE] Chọn URL theo nguồn người dùng chọn ────────────────────
        src = self._cmb_source.currentData()
        if src == "file" and self._video_file_path:
            url = self._video_file_path
        elif src == "file" and not self._video_file_path:
            self._lbl_status.setText("❌ Chưa chọn file video")
            return
        elif src == "webcam":
            url = "0"  # Mặc định mở webcam 0
        # else: src == "db" → dùng url từ camera DB (đã gán ở trên)

        # ── Stream thread ────────────────────────────────────────────────────
        self._stream_thread = StreamClientThread(url, cam_id, parent=self)
        self._stream_thread.frame_ready.connect(self._sv.update_frame)
        self._stream_thread.stream_status.connect(self._on_status)

        # ── Detection worker (ViolationEngine + asyncio loop) ───────────────
        self._detect_worker = DetectionWorker(camera_id=cam_id, parent=self)
        # Nhận raw frame từ stream → AI loop
        self._stream_thread.frame_ready.connect(self._detect_worker.on_frame)
        # Bbox kết quả detect → vẽ overlay trên StreamView
        self._detect_worker.detections_ready.connect(self._sv.set_detections)
        # Vi phạm xác nhận → emit lên MainWindow → ViolationsPanel
        self._detect_worker.violation_saved.connect(self.violation_occurred)
        # FPS AI
        self._detect_worker.ai_fps_updated.connect(
            lambda fps: self._lbl_ai_fps.setText(f"{fps:.1f} fps")
        )
        # Truyền zones hiện tại vào worker
        self._detect_worker.set_zones(self._sv.get_zones_np())
        self._detect_worker.start()

        self._stream_thread.start()
        self._btn_connect.hide()
        self._btn_disconnect.show()

    def _stop_stream(self) -> None:
        if self._detect_worker:
            self._detect_worker.stop()
            self._detect_worker.wait(1000)
            self._detect_worker = None
        if self._stream_thread:
            self._stream_thread.stop()
            self._stream_thread.wait(2000)
            self._stream_thread = None
        self._sv.set_connected(False)
        self._sv.set_detections([])
        self._lbl_status.setText("Đã ngắt kết nối")
        self._lbl_ai_fps.setText("―")
        self._btn_connect.show()
        self._btn_disconnect.hide()

    @pyqtSlot(bool, str)
    def _on_status(self, ok: bool, msg: str) -> None:
        self._sv.set_connected(ok)
        self._lbl_status.setText("🟢 Đang stream" if ok else f"🔴 {msg}")

    @pyqtSlot()
    def _on_frame_counted(self) -> None:
        self._frame_count += 1

    def _tick_fps(self) -> None:
        self._lbl_fps.setText(f"{self._frame_count} fps")
        self._frame_count = 0

    @staticmethod
    def _restyle(w: QWidget) -> None:
        w.style().unpolish(w); w.style().polish(w)

    # ── Traffic ────────────────────────────────────────────────────────────────

    def _send_rpc(self, method: str) -> None:
        """Gửi lệnh RPC tới ESP32_PCB với debounce 800ms."""
        now = time.monotonic()
        if now - self._last_rpc_time < 0.8:
            return
        self._last_rpc_time = now
        # Dùng PCB device name — KHÔNG phải camera device name
        if self._pcb_device:
            self.traffic_rpc_requested.emit(self._pcb_device, method)

    def _send_timing(self) -> None:
        # Dùng PCB device name — KHÔNG phải camera device name
        if self._pcb_device:
            red_ms    = self._sr.value() * 1000
            yellow_ms = self._sy.value() * 1000
            green_ms  = self._sg.value() * 1000
            self.traffic_timing_requested.emit(
                self._pcb_device, red_ms, yellow_ms, green_ms,
            )
            # Lưu timing xuống JSON (dùng camera_id làm key nếu có)
            if self._current_cam:
                settings_store.save_traffic_timing(
                    self._current_cam.get("camera_id", 0),
                    red_ms, yellow_ms, green_ms,
                )

    @pyqtSlot(str, str)
    def on_light_changed(self, device_name: str, state: str) -> None:
        """Nhận trạng thái đèn từ PCB (hoặc camera legacy) → cập nhật UI."""
        self._tl.set_state(state)

    @pyqtSlot(str, bool)
    def on_pcb_status(self, pcb_name: str, online: bool) -> None:
        """PCB online/offline status → cập nhật chỉ báo trong header và groupbox."""
        # Chỉ cập nhật nếu đang ở trạng thái kết nối và tên khớp
        if not self._pcb_connected:
            return
        if self._pcb_device and pcb_name != self._pcb_device:
            return

        # Nhận được telemetry → reset bộ đếm timeout 4s
        if online:
            self._pcb_timeout_timer.start(4000)
            # Lần đầu online sau khi nhấn "Kết nối PCB" → ra lệnh bắt đầu đèn
            if not self._pcb_start_sent:
                self._pcb_start_sent = True
                self.pcb_ping_requested.emit(self._pcb_device, "startTraffic")

        status_text = "Online" if online else "Offline"
        color = "#68d391" if online else "#fc8181"
        icon = "🟢" if online else "🔴"

        self._lbl_pcb_header.setText(f"PCB: {icon} {status_text}")
        self._lbl_pcb_header.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold; margin-right: 15px;")
        self._pcb_status_dot.setText(icon)
        # Enable/disable các nút điều khiển theo trạng thái thực tế
        self._set_traffic_controls_enabled(online)

    def _on_pcb_device_changed(self, text: str) -> None:
        """Khi user thay đổi PCB device name trong textbox."""
        self._pcb_device = text.strip() or "pcb-tl-01"
        # Reset trạng thái về chưa kết nối
        self._set_pcb_ui_disconnected()

    def _on_pcb_connect(self) -> None:
        """Nhấn nút Kết nối PCB — gửi ping và chờ phản hồi telemetry."""
        self._pcb_connected = True
        self._pcb_start_sent = False  # chưa gửi startTraffic
        # Đổi sang UI đang chờ
        self._pcb_status_dot.setText("🟡")
        self._lbl_pcb_header.setText("PCB: 🟡 Đang kết nối...")
        self._lbl_pcb_header.setStyleSheet("color: #f6e05e; font-size: 12px; font-weight: bold; margin-right: 15px;")
        self._btn_pcb_connect.hide()
        self._btn_pcb_disconnect.show()
        # Khóa ô nhập tên khi đang kết nối
        self._pcb_input.setEnabled(False)
        # Gửi lệnh ping để PCB phản hồi ngay
        if self._pcb_device:
            self.pcb_ping_requested.emit(self._pcb_device, "getStatus")
        # Bắt đầu đếm giờ: nếu 4s không có telemetry → offline
        self._pcb_timeout_timer.start(4000)

    def _on_pcb_disconnect(self) -> None:
        """Ngắt theo dõi PCB — gửi lệnh dừng rồi reset UI."""
        # Gửi lệnh dừng đèn vào PCB trước
        if self._pcb_device and self._pcb_connected:
            self.pcb_ping_requested.emit(self._pcb_device, "stopTraffic")
        self._pcb_connected = False
        self._pcb_start_sent = False
        self._pcb_timeout_timer.stop()
        self._set_pcb_ui_disconnected()

    def _on_pcb_timeout(self) -> None:
        """Không nhận được telemetry sau 4s → coi như offline."""
        if self._pcb_connected:
            self._pcb_status_dot.setText("🔴")
            self._lbl_pcb_header.setText("PCB: 🔴 Offline")
            self._lbl_pcb_header.setStyleSheet("color: #fc8181; font-size: 12px; font-weight: bold; margin-right: 15px;")
            self._set_traffic_controls_enabled(False)

    def _set_pcb_ui_disconnected(self) -> None:
        """Reset UI PCB về trạng thái chưa kết nối."""
        self._pcb_status_dot.setText("⚫")
        self._lbl_pcb_header.setText("PCB: ⚫ Offline")
        self._lbl_pcb_header.setStyleSheet("color: #718096; font-size: 12px; font-weight: bold; margin-right: 15px;")
        self._btn_pcb_connect.show()
        self._btn_pcb_disconnect.hide()
        self._pcb_input.setEnabled(True)
        self._set_traffic_controls_enabled(False)

    def _set_traffic_controls_enabled(self, enabled: bool) -> None:
        """Bật/tắt các nút điều khiển đèn giao thông theo trạng thái PCB."""
        self._btn_normal.setEnabled(enabled)
        self._btn_er.setEnabled(enabled)
        self._btn_eg.setEnabled(enabled)
        self._btn_timing.setEnabled(enabled)


    @pyqtSlot(dict)
    def on_traffic_status(self, status: dict) -> None:
        state  = str(status.get("light_state",    "")).upper()
        mode   = str(status.get("operation_mode", "normal"))
        remain = int(status.get("remain_sec",     0))
        if state:  self._tl.set_state(state)
        self._tl.set_mode(mode)
        if remain: self._tl.set_remain(remain)

    # ── Zone editor ────────────────────────────────────────────────────────────

    def _toggle_edit_sl(self) -> None:
        if self._sv._mode == StreamView.MODE_EDIT_SL:
            self._sv.stop_edit()
            self._btn_edit_sl.setText("📏 Stop Line")
            self._btn_edit_sl.setObjectName("btn_primary")
        else:
            self._sv.stop_edit()
            self._sv.start_edit_stop_line()
            self._btn_edit_sl.setText("✅ Xong Stop Line")
            self._btn_edit_sl.setObjectName("btn_success")
            self._btn_edit_dz.setText("🔷 Detect Zone")
            self._btn_edit_dz.setObjectName("btn_primary")
        self._restyle(self._btn_edit_sl)
        self._restyle(self._btn_edit_dz)

    def _toggle_edit_dz(self) -> None:
        if self._sv._mode == StreamView.MODE_EDIT_DZ:
            self._sv.stop_edit()
            self._btn_edit_dz.setText("🔷 Detect Zone")
            self._btn_edit_dz.setObjectName("btn_primary")
        else:
            self._sv.stop_edit()
            self._sv.start_edit_detect_zone()
            self._btn_edit_dz.setText("✅ Xong Detect Zone")
            self._btn_edit_dz.setObjectName("btn_success")
            self._btn_edit_sl.setText("📏 Stop Line")
            self._btn_edit_sl.setObjectName("btn_primary")
        self._restyle(self._btn_edit_sl)
        self._restyle(self._btn_edit_dz)

    def _save_zones(self) -> None:
        self._sv.stop_edit()
        self._btn_edit_sl.setText("📏 Stop Line")
        self._btn_edit_sl.setObjectName("btn_primary")
        self._btn_edit_dz.setText("🔷 Detect Zone")
        self._btn_edit_dz.setObjectName("btn_primary")
        self._restyle(self._btn_edit_sl)
        self._restyle(self._btn_edit_dz)
        # Lưu zones xuống JSON
        if self._current_cam:
            settings_store.save_zones(
                self._current_cam.get("camera_id", 0),
                self._sv.get_zones_np(),
            )

    @pyqtSlot(dict)
    def _on_zone_updated(self, zones: dict) -> None:
        sl = zones.get("stop_line")
        dz = zones.get("detect_zone")
        parts = []
        if sl is not None:
            parts.append(f"Stop line: [{sl[0][0]:.2f},{sl[0][1]:.2f}]→[{sl[1][0]:.2f},{sl[1][1]:.2f}]")
        if dz is not None:
            pts_str = " ".join(f"P{i+1}({dz[i][0]:.2f},{dz[i][1]:.2f})" for i in range(4))
            parts.append(f"Detect zone:\n{pts_str}")
        self._lbl_zone.setText("\n".join(parts) if parts else "Chưa có zone")

        # Cập nhật zones cho detection worker (nếu đang chạy)
        if self._detect_worker is not None:
            self._detect_worker.set_zones(zones)

    # ── Settings persistence ──────────────────────────────────────────────────

    def _load_saved_settings(self, camera_id: int) -> None:
        """Nạp zones + timing đã lưu từ JSON khi chọn camera."""
        # Zones
        zones = settings_store.load_zones(camera_id)
        if zones.get("stop_line") is not None or zones.get("detect_zone") is not None:
            self._sv._sl_pts = None
            self._sv._dz_pts = None
            import numpy as np
            from PyQt5.QtCore import QPointF
            sl = zones.get("stop_line")
            if sl is not None and len(sl) == 2:
                self._sv._sl_pts = [QPointF(float(sl[0][0]), float(sl[0][1])),
                                    QPointF(float(sl[1][0]), float(sl[1][1]))]
            dz = zones.get("detect_zone")
            if dz is not None and len(dz) == 4:
                self._sv._dz_pts = [QPointF(float(dz[i][0]), float(dz[i][1])) for i in range(4)]
            self._sv._orig_w = zones.get("frame_w", 320)
            self._sv._orig_h = zones.get("frame_h", 240)
            self._sv.update()
            self._sv._emit_zones()   # cập nhật label zone

        # Traffic timing
        timing = settings_store.load_traffic_timing(camera_id)
        self._sr.setValue(timing["red_ms"]    // 1000)
        self._sy.setValue(timing["yellow_ms"] // 1000)
        self._sg.setValue(timing["green_ms"]  // 1000)

    def closeEvent(self, event) -> None:
        self._stop_stream()
        super().closeEvent(event)
