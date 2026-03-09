"""Supabase client singleton cho backend."""

from typing import Optional

from supabase import Client, create_client

from utils.logger import get_logger

_client: Optional[Client] = None
logger = get_logger(__name__)


def init_supabase() -> Client:
    """Khởi tạo Supabase client một lần khi startup."""
    global _client

    if _client is None:
        from config.settings import get_settings

        settings = get_settings()
        supabase_key = settings.supabase_service_key or settings.supabase_key
        _client = create_client(settings.supabase_url, supabase_key)

        logger.info(
            "Supabase client đã khởi tạo auth_mode=%s url=%s",
            settings.supabase_auth_mode,
            settings.supabase_url,
        )
        if settings.supabase_auth_mode != "service_role":
            logger.warning(
                "Backend đang dùng SUPABASE_KEY thay vì SUPABASE_SERVICE_KEY. "
                "Các thao tác ghi provisioning/zones có thể thất bại do RLS."
            )

    return _client


def get_supabase() -> Client:
    """Lấy Supabase client instance."""
    if _client is None:
        return init_supabase()
    return _client
