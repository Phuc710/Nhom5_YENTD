from pathlib import Path


# ============================================================
# THONG TIN THU MUC DU AN
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
OUTPUT_DIR = DATA_DIR / "outputs"
MODEL_DIR = BASE_DIR / "models"
LOG_DIR = BASE_DIR / "logs"

DEFAULT_VIDEO_PATH = INPUT_DIR / "video.mp4"
_MODEL_IN_MODELS = MODEL_DIR / "yolov8n.pt"
DEFAULT_MODEL_PATH = _MODEL_IN_MODELS if _MODEL_IN_MODELS.exists() else (BASE_DIR / "yolov8n.pt")


# ============================================================
# CAU HINH NHAN DIEN / TRACKING
# ============================================================
# Chi dem cac loai xe dung voi yeu cau bai toan:
# - car
# - bus
# - truck
# Khong dem motorcycle de tranh sai de bai ban dau.
TARGET_CLASS_NAMES = ("car", "bus", "truck")

# Tracker mac dinh. ByteTrack thuong bam doi tuong on dinh voi video giao thong.
TRACKER_TYPE = "bytetrack.yaml"

# Nguong confidence mac dinh.
CONFIDENCE_THRESHOLD = 0.35


# ============================================================
# CAU HINH HIEN THI / GIAO DIEN
# ============================================================
WINDOW_NAME = "Vehicle Counting System"
HUD_TITLE = "AI TRAFFIC MONITOR"
HUD_SUBTITLE = "YOLOv8 Tracking + Smart Counting"

# Dat None neu muon giu nguyen kich thuoc goc cua video.
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720

# Toa do vach dem tren khung hinh hien thi.
# Day la 2 diem de ban sua cuc nhanh khi doi video.
COUNT_LINE_START = (220, 430)
COUNT_LINE_END = (1080, 430)
LINE_THICKNESS = 4
LINE_CROSS_MARGIN = 10

BOX_THICKNESS = 2
CORNER_RADIUS = 14
TRACE_LENGTH = 12
LABEL_FONT_SCALE = 0.65
LABEL_THICKNESS = 2
TOTAL_FONT_SCALE = 1.2
TOTAL_TEXT_THICKNESS = 3
PANEL_ALPHA = 0.55
HEADER_HEIGHT = 92
FOOTER_HEIGHT = 42
COUNT_PANEL_WIDTH = 275
NEON_GLOW_STEPS = (16, 10, 6)
TRACE_MIN_BOX_AREA = 2600
SMALL_BOX_AREA = 2200
MEDIUM_BOX_AREA = 8500
LABEL_MIN_Y = 30

COLORS = {
    "panel": (10, 18, 28),
    "panel_soft": (22, 32, 46),
    "panel_border": (0, 255, 0),
    "line": (32, 92, 255),
    "line_glow": (0, 180, 255),
    "text_primary": (255, 255, 255),
    "text_secondary": (198, 219, 235),
    "text_muted": (140, 185, 205),
    "text_shadow": (8, 12, 18),
    "car": (0, 231, 255),
    "truck": (0, 170, 255),
    "bus": (95, 255, 165),
    "fallback": (255, 255, 255),
    "success": (80, 255, 180),
    "warning": (0, 210, 255),
}


# ============================================================
# CAU HINH GHI LOG / FILE OUTPUT
# ============================================================
LOG_LEVEL = "INFO"
OUTPUT_CODEC = "mp4v"


def ensure_project_dirs():
    """
    Tao cac thu muc can thiet neu chua ton tai.
    Nhieu he thong production se lam buoc nay ngay tu dau de tranh loi runtime.
    """
    for directory in (INPUT_DIR, OUTPUT_DIR, MODEL_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
