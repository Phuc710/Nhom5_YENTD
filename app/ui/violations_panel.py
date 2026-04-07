"""
Violations Panel — Hiển thị danh sách vi phạm từ Supabase.
Filter theo camera, ngày, biển số. Double-click để xem chi tiết + ảnh.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from PyQt5.QtCore import QThread, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

logger = logging.getLogger(__name__)


class FetchViolationsThread(QThread):
    """Thread tải vi phạm từ Supabase để không block UI."""

    done = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, filters: dict, parent=None) -> None:
        super().__init__(parent)
        self._filters = filters

    def run(self) -> None:
        try:
            from backend.services.violation_service import ViolationService
            import asyncio
            svc = ViolationService()
            violations = asyncio.run(svc.get_violations(limit=200, filters=self._filters))
            self.done.emit(violations)
        except Exception as exc:
            logger.error("Fetch violations failed: %s", exc)
            self.error.emit(str(exc))


class ViolationDetailDialog(QDialog):
    """Hộp thoại xem chi tiết vi phạm và ảnh bằng chứng."""

    def __init__(self, violation: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Chi tiết vi phạm #{violation.get('id', '?')}")
        self.setMinimumSize(720, 500)
        self.setStyleSheet("background-color: #0f1117; color: #e2e8f0;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Images
        img_layout = QVBoxLayout()
        for field, label in [
            ("full_image_url",       "Ảnh toàn cảnh"),
            ("cropped_vehicle_url",  "Xe vi phạm"),
            ("cropped_plate_url",    "Biển số"),
        ]:
            url = violation.get(field) or ""
            img_lbl = QLabel(label)
            img_lbl.setStyleSheet("color: #718096; font-size: 11px; padding-bottom: 2px;")
            img_layout.addWidget(img_lbl)
            pix_lbl = QLabel()
            pix_lbl.setFixedSize(320, 200)
            pix_lbl.setAlignment(Qt.AlignCenter)
            pix_lbl.setStyleSheet("background:#12151f; border:1px solid #2d3748; border-radius:8px;")
            pix_lbl.setText("🖼 Không có ảnh" if not url else "⏳ Đang tải...")
            img_layout.addWidget(pix_lbl)
        img_layout.addStretch()
        layout.addLayout(img_layout)

        # Details
        info_layout = QVBoxLayout()
        fields = [
            ("ID",                str(violation.get("id", "―"))),
            ("Biển số",           violation.get("license_plate") or "―"),
            ("Độ tin cậy",        f"{float(violation.get('confidence') or 0)*100:.1f}%"),
            ("Trạng thái đèn",    (violation.get("traffic_light_state") or "―").upper()),
            ("Camera",            str(violation.get("camera_id") or "―")),
            ("Thời gian",         str(violation.get("timestamp") or "―")),
            ("Loại vi phạm",      violation.get("violation_type") or "―"),
            ("Vote OCR",          str(violation.get("vote_count") or "―")),
        ]
        for key, val in fields:
            row = QHBoxLayout()
            k = QLabel(key + ":")
            k.setFixedWidth(110)
            k.setStyleSheet("color: #718096; font-size: 12px;")
            v = QLabel(val)
            v.setStyleSheet(
                "color: #fc5151; font-weight: bold; font-size: 14px;"
                if key == "Biển số" else "color: #e2e8f0; font-size: 13px;"
            )
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(k)
            row.addWidget(v)
            info_layout.addLayout(row)

        info_layout.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        info_layout.addWidget(btns)
        layout.addLayout(info_layout)


class ViolationsPanel(QWidget):
    """
    Panel danh sách vi phạm:
    - Filter theo camera / ngày bắt đầu / ngày kết thúc / biển số
    - Bảng cuộn với màu đỏ nổi bật cho vi phạm
    - Auto-refresh mỗi 30 giây
    - Double-click → ViolationDetailDialog
    """

    def __init__(self, cameras: list, parent=None) -> None:
        super().__init__(parent)
        self._cameras  = cameras
        self._fetch_thread: Optional[FetchViolationsThread] = None
        self._violations: List[dict] = []

        self._build_ui()

        # Auto refresh
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(30_000)  # 30s
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(16)

        # ── Header ─────────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("🚨  Danh sách vi phạm")
        title.setObjectName("page_title")
        hdr.addWidget(title)
        hdr.addStretch()
        self._lbl_count = QLabel("0 bản ghi")
        self._lbl_count.setStyleSheet("color: #718096; font-size: 12px;")
        hdr.addWidget(self._lbl_count)
        root.addLayout(hdr)

        # ── Filters ────────────────────────────────────────────────────────────
        flt_box = QGroupBox("Bộ lọc")
        flt_lay = QHBoxLayout(flt_box)

        flt_lay.addWidget(QLabel("Camera:"))
        self._cmb_cam = QComboBox()
        self._cmb_cam.addItem("Tất cả", None)
        for cam in self._cameras:
            name = cam.get("camera_name") or f"Cam {cam.get('camera_id')}"
            self._cmb_cam.addItem(name, cam.get("camera_id"))
        flt_lay.addWidget(self._cmb_cam)

        flt_lay.addWidget(QLabel("Từ:"))
        self._date_from = QDateEdit()
        self._date_from.setDate((datetime.now() - timedelta(days=7)).date())
        self._date_from.setCalendarPopup(True)
        flt_lay.addWidget(self._date_from)

        flt_lay.addWidget(QLabel("Đến:"))
        self._date_to = QDateEdit()
        self._date_to.setDate(datetime.now().date())
        self._date_to.setCalendarPopup(True)
        flt_lay.addWidget(self._date_to)

        flt_lay.addWidget(QLabel("Biển số:"))
        self._txt_plate = QLineEdit()
        self._txt_plate.setPlaceholderText("Tìm biển...")
        self._txt_plate.setMaximumWidth(140)
        flt_lay.addWidget(self._txt_plate)

        btn_search = QPushButton("🔍  Tìm kiếm")
        btn_search.setObjectName("btn_primary")
        btn_search.clicked.connect(self.refresh)
        flt_lay.addWidget(btn_search)

        flt_lay.addStretch()
        root.addWidget(flt_box)

        # ── Table ─────────────────────────────────────────────────────────────
        HEADERS = ["ID", "Thời gian", "Biển số", "Camera ID", "Độ tin cậy", "Loại vi phạm", "Đèn"]
        self._table = QTableWidget(0, len(HEADERS))
        self._table.setHorizontalHeaderLabels(HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        self._table.setStyleSheet(
            "QTableWidget { alternate-background-color: #12151f; }"
        )
        root.addWidget(self._table)

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self) -> None:
        filters: dict = {}
        cam_id = self._cmb_cam.currentData()
        if cam_id:
            filters["camera_id"] = cam_id
        plate = self._txt_plate.text().strip()
        if plate:
            filters["license_plate"] = plate
        filters["start_date"] = self._date_from.date().toString(Qt.ISODate)
        filters["end_date"]   = self._date_to.date().toString(Qt.ISODate) + "T23:59:59"

        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        self._fetch_thread = FetchViolationsThread(filters, parent=self)
        self._fetch_thread.done.connect(self._populate_table)
        self._fetch_thread.error.connect(lambda e: logger.error("Fetch error: %s", e))
        self._fetch_thread.start()

    @pyqtSlot(list)
    def _populate_table(self, violations: list) -> None:
        self._violations = violations
        self._table.setRowCount(0)
        self._lbl_count.setText(f"{len(violations)} bản ghi")

        for v in violations:
            row = self._table.rowCount()
            self._table.insertRow(row)

            ts   = str(v.get("timestamp") or "")[:19].replace("T", " ")
            conf = f"{float(v.get('confidence') or 0)*100:.1f}%"
            items = [
                str(v.get("id", "")),
                ts,
                v.get("license_plate") or "― Không đọc được",
                str(v.get("camera_id", "")),
                conf,
                v.get("violation_type") or "red_light",
                (v.get("traffic_light_state") or "").upper(),
            ]

            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 2 and text and "Không" not in text:
                    item.setForeground(QColor("#fc5151"))
                    item.setFont(item.font())
                self._table.setItem(row, col, item)

    def _on_row_double_clicked(self, index) -> None:
        row = index.row()
        if row < len(self._violations):
            dlg = ViolationDetailDialog(self._violations[row], self)
            dlg.exec_()

    def on_new_violation(self, violation: dict) -> None:
        """Gọi từ MainWindow khi có vi phạm mới (realtime)."""
        self._violations.insert(0, violation)
        self._populate_table(self._violations)

    def refresh_cameras(self, cameras: list) -> None:
        """Cập nhật dropdown camera sau khi provision."""
        self._cameras = cameras
        current_data = self._cmb_cam.currentData()
        self._cmb_cam.blockSignals(True)
        self._cmb_cam.clear()
        self._cmb_cam.addItem("Tất cả", None)
        for cam in cameras:
            name = cam.get("camera_name") or f"Cam {cam.get('camera_id')}"
            self._cmb_cam.addItem(name, cam.get("camera_id"))
        # Khôi phục selection cũ nếu có
        for i in range(self._cmb_cam.count()):
            if self._cmb_cam.itemData(i) == current_data:
                self._cmb_cam.setCurrentIndex(i)
                break
        self._cmb_cam.blockSignals(False)
