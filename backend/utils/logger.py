"""Cấu hình logging cho backend."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


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

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Reduce noisy library logs during normal development/runtime.
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("paho").setLevel(logging.WARNING)
    logging.getLogger("realtime").setLevel(logging.WARNING)
    logging.getLogger("realtime._async.client").setLevel(logging.WARNING)
    logging.getLogger("realtime._async.channel").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    if root.handlers:
        return

    file_handler = RotatingFileHandler(
        "logs/backend.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Lấy logger cho từng module."""
    return logging.getLogger(name)
