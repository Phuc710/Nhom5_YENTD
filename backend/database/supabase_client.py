"""Supabase client singleton cho backend."""

from typing import Optional

from supabase import Client, create_client, ClientOptions

from backend.utils.logger import get_logger

_read_client: Optional[Client] = None
_write_client: Optional[Client] = None
logger = get_logger(__name__)


def init_supabase() -> Client:
    """Backward-compatible alias cho write client."""
    return init_supabase_write()


def init_supabase_read() -> Client:
    """Khởi tạo Supabase client cho truy vấn đọc (read-only)."""
    global _read_client

    if _read_client is None:
        from backend.config.settings import get_settings

        settings = get_settings()
        # Tăng timeout và cấu hình để tránh lỗi SSL/EOF trên Windows
        options = ClientOptions(postgrest_client_timeout=30)
        _read_client = create_client(settings.supabase_url, settings.supabase_key, options=options)
        logger.info("Supabase read client đã khởi tạo url=%s (timeout=30s)", settings.supabase_url)

    return _read_client


def init_supabase_write() -> Client:
    """Khởi tạo Supabase client cho thao tác ghi/quản trị (service_role)."""
    global _write_client

    if _write_client is None:
        from backend.config.settings import get_settings

        settings = get_settings()
        supabase_key = settings.supabase_service_key or settings.supabase_key
        # Tăng timeout và cấu hình để tránh lỗi SSL/EOF trên Windows
        options = ClientOptions(postgrest_client_timeout=30)
        _write_client = create_client(settings.supabase_url, supabase_key, options=options)

        logger.info(
            "Supabase write client đã khởi tạo url=%s (auth_mode=%s, timeout=30s)",
            settings.supabase_url,
            settings.supabase_auth_mode,
        )
        if settings.supabase_auth_mode != "service_role":
            logger.warning(
                "Backend đang dùng SUPABASE_KEY thay vì SUPABASE_SERVICE_KEY. "
                "Các thao tác ghi thông tin camera hoặc vùng nhận diện có thể thất bại do chính sách RLS."
            )

    return _write_client


def get_supabase() -> Client:
    """Bí danh tương thích ngược cho write client."""
    return get_supabase_write()


def get_supabase_read() -> Client:
    """Lấy instance của Supabase read client."""
    if _read_client is None:
        return init_supabase_read()
    return _read_client


def get_supabase_write() -> Client:
    """Lấy instance của Supabase write client."""
    if _write_client is None:
        return init_supabase_write()
    return _write_client
