"""
Entry point — Khởi động PyQt5 Traffic Monitor App.
"""
import logging
import os
import sys
from pathlib import Path

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname).1s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Tắt noise từ thư viện bên ngoài
for _lib in ("urllib3", "httpx", "httpcore", "hpack", "paho", "matplotlib",
             "PIL", "asyncio", "websockets", "charset_normalizer"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

# Thêm root project vào sys.path để import backend.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env trước khi import backend
from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

from app.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Traffic Violation Monitor")
    app.setOrganizationName("YTD")
    app.setFont(QFont("Segoe UI", 10))

    qss_path = Path(__file__).parent / "assets" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    logger.info("starting app")
    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
