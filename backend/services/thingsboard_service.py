"""Dịch vụ gọi REST API ThingsBoard cho các thao tác điều khiển và đồng bộ thiết bị."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ThingsBoardService:
    """Gói gọn các lời gọi REST từ backend sang ThingsBoard."""

    _ATTRIBUTE_KEYS = (
        "camera_id",
        "device_model",
        "device_name",
        "project_name",
        "tb_device_name",
        "fw_version",
        "idf_version",
        "idf_ver",
        "wifi_ssid",
        "resolution",
        "mac_address",
        "location",
        "reset_reason",
        "ip_address",
        "stream_url",
        "stream_scheme",
        "stream_host",
        "stream_port",
        "stream_path",
        "stream_snapshot_path",
        "capture_interval_ms",
        "jpeg_quality",
        "telemetry_interval_ms",
        "tl_red_ms",
        "tl_yellow_ms",
        "tl_green_ms",
        "target_fw_version",
        "ota_url",
        "device_status",
        "backend_sync",
    )
    _TIMESERIES_KEYS = (
        "status",
        "device_state",
        "cpu_temp",
        "free_heap",
        "min_free_heap",
        "uptime_s",
        "Light_Mode",
        "ip_address",
        "stream_url",
        "device_name",
        "tb_device_name",
        "backend_sync",
        "wifi_rssi",
        "wifi_disconnect_count",
        "traffic_light_state",
        "operation_mode",
        "tl_state_ms",
    )

    def __init__(self) -> None:
        self._base_url = settings.thingsboard_url.rstrip("/")
        self._username = settings.thingsboard_username
        self._password = settings.thingsboard_password
        self._timeout = 15.0
        self._page_size = settings.thingsboard_sync_page_size

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

    def list_devices(self) -> List[Dict[str, Any]]:
        """Lấy toàn bộ thiết bị tenant hiện có trên ThingsBoard theo phân trang."""
        with httpx.Client(base_url=self._base_url, timeout=self._timeout) as client:
            token = self._login(client)
            headers = {"X-Authorization": f"Bearer {token}"}
            page = 0
            devices: List[Dict[str, Any]] = []

            while True:
                response = client.get(
                    "/api/tenant/deviceInfos",
                    params={
                        "pageSize": self._page_size,
                        "page": page,
                        "sortProperty": "createdTime",
                        "sortOrder": "DESC",
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json() or {}
                batch = payload.get("data") or []

                for device in batch:
                    runtime = self._fetch_device_runtime(client, headers, device)
                    if runtime:
                        device["runtime"] = runtime

                devices.extend(batch)

                if not payload.get("hasNext"):
                    break
                page += 1

        return devices

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

    def _fetch_device_runtime(
        self,
        client: httpx.Client,
        headers: Dict[str, str],
        device: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Lấy thêm attributes và telemetry mới nhất để backend bám sát runtime hơn."""
        device_id = self._extract_device_id(device)
        if not device_id:
            return {}

        runtime: Dict[str, Any] = {}
        attribute_keys = ",".join(self._ATTRIBUTE_KEYS)
        timeseries_keys = ",".join(self._TIMESERIES_KEYS)

        for scope in ("CLIENT_SCOPE", "SHARED_SCOPE"):
            try:
                response = client.get(
                    f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes/{scope}",
                    params={"keys": attribute_keys},
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.debug("Không đọc được attributes scope=%s cho device=%s: %s", scope, device_id, exc)
                continue

            runtime.update(self._parse_attribute_entries(response.json()))

        try:
            response = client.get(
                f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
                params={
                    "keys": timeseries_keys,
                    "limit": 1,
                    "agg": "NONE",
                    "useStrictDataTypes": "true",
                },
                headers=headers,
            )
            response.raise_for_status()
            runtime.update(self._parse_latest_timeseries(response.json()))
        except httpx.HTTPError as exc:
            logger.debug("Không đọc được telemetry cho device=%s: %s", device_id, exc)

        return runtime

    @staticmethod
    def _extract_device_id(device: Dict[str, Any]) -> str:
        raw_id = device.get("id")
        if isinstance(raw_id, dict):
            return str(raw_id.get("id") or "")
        return str(raw_id or "")

    @staticmethod
    def _parse_attribute_entries(payload: Any) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                if key:
                    data[str(key)] = item.get("value")
            return data

        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    data.update(ThingsBoardService._parse_attribute_entries(value))
                elif isinstance(value, dict):
                    data.update(value)
        return data

    @staticmethod
    def _parse_latest_timeseries(payload: Any) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if not isinstance(payload, dict):
            return data

        for key, entries in payload.items():
            if isinstance(entries, list) and entries:
                latest = entries[0] or {}
                data[str(key)] = latest.get("value")
            elif entries is not None:
                data[str(key)] = entries
        return data
