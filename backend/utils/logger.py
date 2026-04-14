"""Cấu hình logging cho backend — format UVI style."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Map level → ký tự đơn kiểu UVI
_LEVEL_ABBR = {
    logging.DEBUG:    "D",
    logging.INFO:     "I",
    logging.WARNING:  "W",
    logging.ERROR:    "E",
    logging.CRITICAL: "C",
}


class _UviFormatter(logging.Formatter):
    """Format: HH:MM:SS [I] module.name: message"""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        abbr = _LEVEL_ABBR.get(record.levelno, "?")
        ts   = self.formatTime(record, datefmt="%H:%M:%S")
        msg  = record.getMessage()
        # Exc info nếu có
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg = f"{msg}\n{record.exc_text}"
        return f"{ts} [{abbr}] {record.name}: {msg}"


def _configure_console_encoding() -> None:
    """Buộc stdout/stderr dùng UTF-8 nếu môi trường hỗ trợ."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def setup_logging(log_level: str = "INFO") -> None:
    """Khởi tạo logging toàn cục cho backend."""
    os.makedirs("logs", exist_ok=True)
    _configure_console_encoding()

    uvi_fmt  = _UviFormatter()
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # ── Giảm noise từ thư viện bên thứ 3 ──────────────────────────────
    for noisy in (
        "watchfiles.main", "httpx", "httpcore", "ultralytics",
        "asyncio", "uvicorn.access", "paho",
        "realtime", "realtime._async.client", "realtime._async.channel",
        "websockets", "matplotlib",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if root.handlers:
        return

    # File handler (giữ full format để dễ grep)
    file_handler = RotatingFileHandler(
        "logs/backend.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    # Console handler — UVI style
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(uvi_fmt)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Lấy logger cho từng module."""
    return logging.getLogger(name)
