"""Dịch vụ gọi REST API ThingsBoard cho các thao tác điều khiển thiết bị."""

from __future__ import annotations

from typing import Any, Dict

import httpx

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ThingsBoardService:
    """Gói gọn các lời gọi REST từ backend sang ThingsBoard."""

    def __init__(self) -> None:
        self._base_url = settings.thingsboard_url.rstrip("/")
        self._username = settings.thingsboard_username
        self._password = settings.thingsboard_password
        self._timeout = 15.0

    def factory_reset_device(self, tb_device_name: str) -> Dict[str, Any]:
        """Gửi RPC `factoryReset` tới thiết bị ThingsBoard theo tên."""
        if not tb_device_name:
            raise ValueError("Camera chưa có tên thiết bị ThingsBoard để gửi lệnh factory reset")

        with httpx.Client(base_url=self._base_url, timeout=self._timeout) as client:
            token = self._login(client)
            device_id = self._resolve_device_id(client, token, tb_device_name)
            payload = {"method": "factoryReset", "params": {}}
            response = client.post(
                f"/api/rpc/oneway/{device_id}",
                json=payload,
                headers={"X-Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

        logger.warning("Đã gửi lệnh factory reset tới ThingsBoard device=%s", tb_device_name)
        return {
            "ok": True,
            "action": "factory_reset",
            "tb_device_name": tb_device_name,
            "message": "Đã gửi lệnh factory reset tới thiết bị. Thiết bị sẽ xóa toàn bộ NVS rồi khởi động lại.",
        }

    def _login(self, client: httpx.Client) -> str:
        response = client.post(
            "/api/auth/login",
            json={"username": self._username, "password": self._password},
        )
        response.raise_for_status()

        data = response.json()
        token = data.get("token")
        if not token:
            raise RuntimeError("ThingsBoard không trả về JWT token")
        return token

    def _resolve_device_id(self, client: httpx.Client, token: str, tb_device_name: str) -> str:
        response = client.get(
            "/api/tenant/devices",
            params={"deviceName": tb_device_name},
            headers={"X-Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        data = response.json()
        device_id = (((data or {}).get("id")) or {}).get("id")
        if not device_id:
            raise ValueError(f"Không tìm thấy thiết bị ThingsBoard: {tb_device_name}")
        return device_id
