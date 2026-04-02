"""
ThingsBoard Service — Business logic cao cấp dùng ThingsBoardClient.

Trách nhiệm:
  - Đồng bộ thiết bị (list_devices)
  - Gửi lệnh RPC (reboot, factory_reset, OTA, traffic light)
  - Đọc/ghi Shared Attributes (cấu hình thiết bị)

Public API của class này KHÔNG thay đổi — camera_service.py dùng bình thường.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.services.thingsboard_client import ThingsBoardClient
from backend.config.settings import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ThingsBoardService:
    """
    Lớp nghiệp vụ ThingsBoard:
      - Inventory  : list_devices()
      - RPC        : reboot, factory_reset, OTA, traffic_light
      - Config     : update_shared_attributes()
    """

    # Attribute keys cần lấy khi sync thiết bị
    _ATTRIBUTE_KEYS = (
        "camera_id", "device_model", "device_name", "project_name",
        "tb_device_name", "fw_version", "idf_version", "idf_ver",
        "wifi_ssid", "resolution", "mac_address", "location",
        "reset_reason", "ip_address", "stream_url", "stream_scheme",
        "stream_host", "stream_port", "stream_path", "stream_snapshot_path",
        "capture_interval_ms", "jpeg_quality", "telemetry_interval_ms",
        "tl_red_ms", "tl_yellow_ms", "tl_green_ms",
        "target_fw_version", "ota_url", "device_status", "backend_sync",
    )
    # Timeseries keys cần lấy khi sync thiết bị
    _TIMESERIES_KEYS = (
        "status", "device_state", "cpu_temp", "free_heap", "min_free_heap",
        "uptime_s", "Light_Mode", "ip_address", "stream_url", "device_name",
        "tb_device_name", "backend_sync", "wifi_rssi", "wifi_disconnect_count",
        "traffic_light_state", "operation_mode", "tl_state_ms",
    )
    # RPC method map cho đèn giao thông
    _TRAFFIC_LIGHT_RPC = {
        "normal": "setNormalMode",
        "red":    "setEmergencyRed",
        "green":  "setEmergencyGreen",
    }

    def __init__(self) -> None:
        self._client = ThingsBoardClient()
        self._page_size = settings.thingsboard_sync_page_size

    async def close(self) -> None:
        await self._client.close()

    # ==================================================================
    # Inventory — đồng bộ thiết bị
    # ==================================================================

    async def list_devices(self) -> List[Dict[str, Any]]:
        """Lấy toàn bộ thiết bị của tenant, kèm runtime attributes."""
        devices: List[Dict[str, Any]] = []
        page = 0

        while True:
            resp = await self._client.get(
                "/api/tenant/deviceInfos",
                params={
                    "pageSize": self._page_size,
                    "page": page,
                    "sortProperty": "createdTime",
                    "sortOrder": "DESC",
                },
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            batch: List[Dict[str, Any]] = payload.get("data") or []

            for device in batch:
                runtime = await self._fetch_runtime(device)
                if runtime:
                    device["runtime"] = runtime

            devices.extend(batch)
            if not payload.get("hasNext"):
                break
            page += 1

        logger.info("📊 [TB] ✅ Đã quét %d thiết bị", len(devices))
        return devices

    # ==================================================================
    # RPC — điều khiển thiết bị từ xa
    # ==================================================================

    async def reboot_device(self, tb_device_name: str) -> Dict[str, Any]:
        return await self._rpc(tb_device_name, "reboot", action="reboot")

    async def factory_reset_device(self, tb_device_name: str) -> Dict[str, Any]:
        return await self._rpc(tb_device_name, "factoryReset", action="factory_reset")

    async def start_ota_update(self, tb_device_name: str, url: str) -> Dict[str, Any]:
        return await self._rpc(tb_device_name, "startOTA", params={"url": url}, action="ota")

    async def set_traffic_light_mode(self, tb_device_name: str, mode: str) -> Dict[str, Any]:
        method = self._TRAFFIC_LIGHT_RPC.get(mode.lower())
        if not method:
            raise ValueError(f"Chế độ đèn không hợp lệ: {mode!r} (phải là: normal/red/green)")
        return await self._rpc(tb_device_name, method, action="traffic_light")

    # ==================================================================
    # Shared Attributes — đọc/ghi cấu hình thiết bị
    # ==================================================================

    async def update_shared_attributes(
        self, tb_device_name: str, attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ghi Shared Attributes lên ThingsBoard (cấu hình tĩnh cho ESP32)."""
        if not tb_device_name:
            raise ValueError("Thiết bị chưa có tên ThingsBoard")

        device_id = await self._client.resolve_device_id(tb_device_name)
        resp = await self._client.post(
            f"/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE",
            json=attributes,
        )
        resp.raise_for_status()
        logger.info("⚙️ [TB] Cập nhật Shared Attributes | device=%s | keys=%s",
                    tb_device_name, list(attributes.keys()))
        return {"ok": True, "tb_device_name": tb_device_name, "attributes": attributes}

    # ==================================================================
    # Internal helpers
    # ==================================================================

    async def _rpc(
        self,
        tb_device_name: str,
        method: str,
        params: Dict[str, Any] | None = None,
        action: str = "rpc",
    ) -> Dict[str, Any]:
        """Gửi một lệnh RPC one-way tới thiết bị."""
        if not tb_device_name:
            raise ValueError(f"Camera chưa có identity ThingsBoard để gửi RPC {method!r}")

        device_id = await self._client.resolve_device_id(tb_device_name)
        resp = await self._client.post(
            f"/api/rpc/oneway/{device_id}",
            json={"method": method, "params": params or {}},
        )
        resp.raise_for_status()
        logger.info("📡 [TB] RPC %s → %s", method, tb_device_name)
        return {
            "ok": True,
            "action": action,
            "method": method,
            "tb_device_name": tb_device_name,
            "message": f"Đã gửi lệnh {method} thành công.",
        }

    async def _fetch_runtime(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Lấy attributes + telemetry mới nhất của một thiết bị."""
        device_id = self._extract_device_id(device)
        if not device_id:
            return {}

        runtime: Dict[str, Any] = {}

        # CLIENT + SHARED attributes
        for scope in ("CLIENT_SCOPE", "SHARED_SCOPE"):
            try:
                resp = await self._client.get(
                    f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes/{scope}",
                    params={"keys": ",".join(self._ATTRIBUTE_KEYS)},
                )
                resp.raise_for_status()
                runtime.update(_parse_attributes(resp.json()))
            except Exception:
                continue

        # Latest timeseries
        try:
            resp = await self._client.get(
                f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
                params={
                    "keys": ",".join(self._TIMESERIES_KEYS),
                    "limit": 1,
                    "agg": "NONE",
                    "useStrictDataTypes": "true",
                },
            )
            resp.raise_for_status()
            runtime.update(_parse_timeseries(resp.json()))
        except Exception:
            pass

        return runtime

    @staticmethod
    def _extract_device_id(device: Dict[str, Any]) -> str:
        raw = device.get("id")
        if isinstance(raw, dict):
            return str(raw.get("id") or "")
        return str(raw or "")


# ==================================================================
# Pure parse helpers (module-level, không cần self)
# ==================================================================

def _parse_attributes(payload: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("key"):
                key = str(item["key"])
                val = item.get("value")
                if key == "idf_ver":
                    data["idf_version"] = val   # alias
                data[key] = val
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                data.update(_parse_attributes(value))
            elif isinstance(value, dict):
                data.update(value)
    return data


def _parse_timeseries(payload: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not isinstance(payload, dict):
        return data
    for key, entries in payload.items():
        if isinstance(entries, list) and entries:
            val = (entries[0] or {}).get("value")
            key_str = str(key)
            if key_str == "Light_Mode":
                data["light_mode"] = val    # normalize key
            data[key_str] = val
    return data
