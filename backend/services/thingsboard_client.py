"""
ThingsBoard HTTP Client — Lớp thấp, quản lý auth và base requests.

Trách nhiệm:
  - Đăng nhập, lấy JWT token và cache lại (tránh login mỗi request)
  - Cung cấp get() / post() đã xác thực cho lớp service bên trên
  - Giải phóng httpx.AsyncClient khi stop

KHÔNG chứa business logic (RPC, sync, v.v.) — lớp này thuần HTTP.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from backend.config.settings import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Token ThingsBoard có hiệu lực ~1 giờ; ta refresh trước 5 phút
_TOKEN_TTL_SECONDS = 55 * 60


class ThingsBoardClient:
    """Async HTTP client cho ThingsBoard REST API, tự động quản lý JWT."""

    def __init__(self) -> None:
        self._base_url  = settings.thingsboard_url.rstrip("/")
        self._username  = settings.thingsboard_username
        self._password  = settings.thingsboard_password
        self._timeout   = 15.0
        self._client:   Optional[httpx.AsyncClient] = None
        # Token cache
        self._token:        Optional[str] = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._token  = None

    # ------------------------------------------------------------------
    # Authenticated requests (dùng cho service layer)
    # ------------------------------------------------------------------

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["X-Authorization"] = f"Bearer {await self._get_token()}"
        return await self._http_client().get(path, headers=headers, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["X-Authorization"] = f"Bearer {await self._get_token()}"
        return await self._http_client().post(path, headers=headers, **kwargs)

    # ------------------------------------------------------------------
    # Device ID resolver (helper dùng nhiều nơi)
    # ------------------------------------------------------------------

    async def resolve_device_id(self, tb_device_name: str) -> str:
        """Trả UUID của device theo tên; raise ValueError nếu không tìm thấy."""
        resp = await self.get("/api/tenant/devices", params={"deviceName": tb_device_name})
        resp.raise_for_status()
        data = resp.json() or {}
        device_id = ((data.get("id")) or {}).get("id")
        if not device_id:
            raise ValueError(f"Không tìm thấy thiết bị ThingsBoard: {tb_device_name}")
        return str(device_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def _get_token(self) -> str:
        """Trả token còn hiệu lực; tự login lại khi hết hạn."""
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        self._token = await self._login()
        self._token_expiry = time.monotonic() + _TOKEN_TTL_SECONDS
        return self._token

    async def _login(self) -> str:
        resp = await self._http_client().post(
            "/api/auth/login",
            json={"username": self._username, "password": self._password},
        )
        resp.raise_for_status()
        token = (resp.json() or {}).get("token")
        if not token:
            raise RuntimeError("ThingsBoard không trả về JWT token")
        logger.debug("🔑 [TB] Đăng nhập thành công (token mới)")
        return str(token)
