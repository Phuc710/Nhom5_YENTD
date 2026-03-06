"""
utils/logger.py — Logging cấu hình với file rotation
"""
import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logging(log_level: str = "INFO") -> None:
    """Setup application logging — gọi 1 lần khi khởi động"""
    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Tránh duplicate handlers nếu setup_logging gọi nhiều lần
    if root.handlers:
        return

    # File handler
    file_handler = RotatingFileHandler(
        "logs/backend.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Lấy logger cho module cụ thể"""
    return logging.getLogger(name)
