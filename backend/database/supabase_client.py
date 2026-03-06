"""
database/supabase_client.py — Supabase client singleton
"""
from supabase import create_client, Client
from typing import Optional

_client: Optional[Client] = None


def init_supabase() -> Client:
    """Khởi tạo Supabase client — gọi 1 lần khi startup"""
    global _client
    if _client is None:
        from config.settings import get_settings
        s = get_settings()
        _client = create_client(s.supabase_url, s.supabase_service_key or s.supabase_key)
    return _client


def get_supabase() -> Client:
    """Lấy Supabase client instance"""
    if _client is None:
        return init_supabase()
    return _client
