"""Supabase client singleton cho backend."""

from typing import Optional

from supabase import Client, create_client

from backend.utils.logger import get_logger

_read_client: Optional[Client] = None
_write_client: Optional[Client] = None
logger = get_logger(__name__)


def init_supabase() -> Client:
    """Backward-compatible alias cho write client."""
    return init_supabase_write()


def init_supabase_read() -> Client:
    """Khoi tao Supabase client cho truy van read-only."""
    global _read_client

    if _read_client is None:
        from backend.config.settings import get_settings

        settings = get_settings()
        _read_client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase read client da khoi tao url=%s", settings.supabase_url)

    return _read_client


def init_supabase_write() -> Client:
    """Khoi tao Supabase client cho thao tac ghi/privileged."""
    global _write_client

    if _write_client is None:
        from backend.config.settings import get_settings

        settings = get_settings()
        supabase_key = settings.supabase_service_key or settings.supabase_key
        _write_client = create_client(settings.supabase_url, supabase_key)

        logger.info(
            "Supabase write client da khoi tao auth_mode=%s url=%s",
            settings.supabase_auth_mode,
            settings.supabase_url,
        )
        if settings.supabase_auth_mode != "service_role":
            logger.warning(
                "Backend dang dung SUPABASE_KEY thay vi SUPABASE_SERVICE_KEY. "
                "Cac thao tac ghi provisioning/zones co the that bai do RLS."
            )

    return _write_client


def get_supabase() -> Client:
    """Backward-compatible alias cho write client."""
    return get_supabase_write()


def get_supabase_read() -> Client:
    """Lay Supabase read client instance."""
    if _read_client is None:
        return init_supabase_read()
    return _read_client


def get_supabase_write() -> Client:
    """Lay Supabase write client instance."""
    if _write_client is None:
        return init_supabase_write()
    return _write_client
