from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtCore import QThread, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class FetchStatsThread(QThread):
    done = pyqtSignal(dict)

    def run(self) -> None:
        try:
            # Tạo fresh client cho thread này (httpx không thread-safe)
            from backend.config.settings import get_settings
            from supabase import create_client, ClientOptions
            settings = get_settings()
            db = create_client(
                settings.supabase_url, settings.supabase_key,
                options=ClientOptions(postgrest_client_timeout=30),
            )

            now   = datetime.now()
            today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            week  = (now - timedelta(days=7)).isoformat()
            month = (now - timedelta(days=30)).isoformat()

            total  = db.table("violations").select("id", count="exact").execute().count or 0
            today_ = db.table("violations").select("id", count="exact").gte("timestamp", today).execute().count or 0
            week_  = db.table("violations").select("id", count="exact").gte("timestamp", week).execute().count or 0
            month_ = db.table("violations").select("id", count="exact").gte("timestamp", month).execute().count or 0

            # Theo giờ trong ngày hôm nay (last 12h)
            recent = db.table("violations").select("timestamp").gte("timestamp", (now - timedelta(hours=12)).isoformat()).execute()
            hourly: Dict[int, int] = {h: 0 for h in range(24)}
            for row in recent.data or []:
                try:
                    h = int(row["timestamp"][11:13])
                    hourly[h] = hourly.get(h, 0) + 1
                except Exception:
                    pass

            self.done.emit({
                "total": total,
                "today": today_,
                "week":  week_,
                "month": month_,
                "hourly": hourly,
            })
        except Exception as exc:
            logger.error("Stats fetch failed: %s", exc)
            self.done.emit({})


class StatCard(QFrame):
    """Card hiển thị 1 chỉ số."""

    def __init__(self, icon: str, label: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        top = QHBoxLayout()
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size: 20px; background: transparent;")
        lbl_title = QLabel(label)
        lbl_title.setObjectName("card_title")
        top.addWidget(lbl_icon)
        top.addWidget(lbl_title)
        top.addStretch()
        layout.addLayout(top)

        self._val_lbl = QLabel("—")
        self._val_lbl.setStyleSheet(
            f"font-size: 32px; font-weight: 700; color: {color}; background: transparent;"
        )
        layout.addWidget(self._val_lbl)

        sub = QLabel("đang tải...")
        sub.setStyleSheet("color: #718096; font-size: 11px; background: transparent;")
        self._sub_lbl = sub
        layout.addWidget(sub)

    def set_value(self, value: int, sub: str = "") -> None:
        self._val_lbl.setText(f"{value:,}".replace(",", "."))
        if sub:
            self._sub_lbl.setText(sub)


class DashboardPanel(QWidget):
    """Panel thống kê tổng quan với stat cards và biểu đồ."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fetch_thread = None
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load_stats)
        self._timer.start(60_000)  # 1 phút
        self._load_stats()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(20)

        title = QLabel("📊  Dashboard Thống kê")
        title.setObjectName("page_title")
        root.addWidget(title)

        # Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(16)

        self._card_total = StatCard("🚨", "TỔNG VI PHẠM", "#fc8181")
        self._card_today = StatCard("📅", "HÔM NAY", "#f6e05e")
        self._card_week  = StatCard("📆", "7 NGÀY QUA", "#63b3ed")
        self._card_month = StatCard("🗓️", "30 NGÀY QUA", "#68d391")

        cards_grid.addWidget(self._card_total, 0, 0)
        cards_grid.addWidget(self._card_today, 0, 1)
        cards_grid.addWidget(self._card_week,  0, 2)
        cards_grid.addWidget(self._card_month, 0, 3)
        root.addLayout(cards_grid)

        # Chart
        chart_lbl = QLabel("Phân bố vi phạm theo giờ (12h qua)")
        chart_lbl.setStyleSheet("color: #a0aec0; font-size: 13px; font-weight: 600;")
        root.addWidget(chart_lbl)

        self._fig = Figure(facecolor="#1a1d27", figsize=(10, 3))
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setMinimumHeight(250)
        self._canvas.setStyleSheet("border: 1px solid #2d3748; border-radius: 8px;")
        root.addWidget(self._canvas)

        root.addStretch()

    def _load_stats(self) -> None:
        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        self._fetch_thread = FetchStatsThread(self)
        self._fetch_thread.done.connect(self._on_stats)
        self._fetch_thread.start()

    @pyqtSlot(dict)
    def _on_stats(self, stats: dict) -> None:
        self._card_total.set_value(stats.get("total", 0), "tổng cộng")
        self._card_today.set_value(stats.get("today", 0), "trong ngày")
        self._card_week.set_value(stats.get("week", 0), "7 ngày gần nhất")
        self._card_month.set_value(stats.get("month", 0), "30 ngày gần nhất")
        self._build_chart(stats.get("hourly", {}))

    def _build_chart(self, hourly: dict) -> None:
        now_h = datetime.now().hour
        hours = [(now_h - 11 + i) % 24 for i in range(12)]
        values = [hourly.get(h, 0) for h in hours]
        labels = [f"{h:02d}:00" for h in hours]

        self._ax.clear()
        self._ax.set_facecolor("#12151f")
        bars = self._ax.bar(labels, values, color="#fc5151", edgecolor="#fc5151", alpha=0.85)
        self._ax.set_ylabel("Vi phạm", color="#a0aec0", fontsize=9)
        self._ax.tick_params(colors="#a0aec0", labelsize=8)
        self._ax.spines[:].set_color("#2d3748")
        self._ax.yaxis.label.set_color("#a0aec0")
        self._fig.tight_layout(pad=1.0)
        self._canvas.draw()

    def on_new_violation(self, violation: dict) -> None:
        """Gọi từ MainWindow khi có vi phạm mới → refresh stats."""
        self._load_stats()
