import os
import sys
import logging
from pathlib import Path

# 1. Setup Path & Environment
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))  # API layer dùng 'from api.xxx' imports

from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

# 2. Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname).1s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Launcher")

def main():
    # 3. Pre-load AI models & DLLs in Main Thread (TOP PRIORITY)
    # Rất quan trọng trên Windows: phải load torch và onnxruntime ở Main Thread
    # trước khi bất kỳ thread nào khác (như DetectionWorker) được tạo để tránh lỗi DLL.
    try:
        print("--- [Launcher] Pre-loading AI libraries (Torch + ONNXRuntime) ---")
        import torch
        import onnxruntime
        from backend.ml.detector import get_detector
        get_detector()
        print("--- [Launcher] AI libraries loaded successfully ---")
    except Exception as e:
        print(f"--- [Launcher] Failed to load AI libraries: {e} ---")

    # 4. Start GUI
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFont
    
    app = QApplication(sys.argv)
    app.setApplicationName("Traffic Violation Monitor")
    app.setFont(QFont("Segoe UI", 10))

    # Load QSS
    qss_path = ROOT / "app" / "assets" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    # Load MainWindow
    from app.ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
