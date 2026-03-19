"""Sync shared local config from backend/.env to frontend and ESP32 files."""

from __future__ import annotations

import configparser
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV_PATH = REPO_ROOT / "backend" / ".env"
FRONTEND_ENV_PATH = REPO_ROOT / "frontend" / ".env"
PLATFORMIO_PATH = REPO_ROOT / "esp32-s3-devkitc-1" / "platformio.ini"
PLATFORMIO_TEMPLATE_PATH = REPO_ROOT / "esp32-s3-devkitc-1" / "platformio.ini.example"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def resolve_local_lan_ip(env: dict[str, str]) -> str:
    return env.get("LOCAL_LAN_IP", "").strip()


def resolve_public_api_url(env: dict[str, str]) -> str:
    public_url = env.get("PUBLIC_API_URL", "").strip().rstrip("/")
    if public_url:
        return public_url

    local_lan_ip = resolve_local_lan_ip(env)
    if local_lan_ip:
        port = env.get("PORT", "8000").strip() or "8000"
        return f"http://{local_lan_ip}:{port}"

    host = env.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = env.get("PORT", "8000").strip() or "8000"
    if host in {"0.0.0.0", "::", ""}:
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def resolve_thingsboard_url(env: dict[str, str]) -> str:
    configured_url = env.get("THINGSBOARD_URL", "").strip().rstrip("/")
    if configured_url:
        return configured_url

    local_lan_ip = resolve_local_lan_ip(env)
    if local_lan_ip:
        return f"http://{local_lan_ip}:9090"
    return "http://localhost:9090"


def resolve_thingsboard_mqtt_uri(env: dict[str, str], tb_url: str) -> str:
    host = env.get("MQTT_TB_HOST", "").strip()
    port = env.get("MQTT_TB_PORT", "1883").strip() or "1883"
    if not host:
        parsed = urlparse(tb_url)
        host = parsed.hostname or resolve_local_lan_ip(env) or "localhost"
    return f"mqtt://{host}:{port}"


def to_esp_ip_macro(value: str, fallback: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return fallback
    if normalized.startswith("ESP_IP4TOADDR("):
        return normalized
    parts = normalized.split(".")
    if len(parts) != 4:
        return fallback
    try:
        octets = [str(int(part)) for part in parts]
    except ValueError:
        return fallback
    return f"ESP_IP4TOADDR({', '.join(octets)})"


def write_frontend_env(api_url: str, frontend_api_mode: str) -> None:
    FRONTEND_ENV_PATH.write_text(
        "# Auto-generated from backend/.env by backend/scripts/sync_local_config.py\n"
        f"FRONTEND_API_MODE={frontend_api_mode}\n"
        f"API_URL={api_url}\n",
        encoding="utf-8",
    )


def load_platformio_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    source = PLATFORMIO_PATH if PLATFORMIO_PATH.exists() else PLATFORMIO_TEMPLATE_PATH
    parser.read(source, encoding="utf-8")
    return parser


def ensure_section(parser: configparser.ConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def write_platformio_ini(env: dict[str, str], api_url: str) -> None:
    parser = load_platformio_config()

    tb_url = resolve_thingsboard_url(env)
    tb_mqtt_uri = resolve_thingsboard_mqtt_uri(env, tb_url)
    tb_provision_url = f"{tb_url}/api/v1/provision"

    for section in ("secrets", "backend", "thingsboard", "device_defaults", "advanced_settings", "network"):
        ensure_section(parser, section)

    parser.set("secrets", "wifi_ap_ssid", env.get("ESP_WIFI_AP_SSID", parser.get("secrets", "wifi_ap_ssid", fallback="ESP32_Config")))
    parser.set("secrets", "wifi_ap_pass", env.get("ESP_WIFI_AP_PASS", parser.get("secrets", "wifi_ap_pass", fallback="12345678")))
    parser.set("secrets", "backend_url", api_url)

    parser.set("backend", "base_url", api_url)
    parser.set("backend", "device_prefix", env.get("ESP_DEVICE_PREFIX", parser.get("backend", "device_prefix", fallback="PCB Cam")))
    parser.set("backend", "device_model", env.get("ESP_DEVICE_MODEL", parser.get("backend", "device_model", fallback="PCB S3")))

    parser.set("thingsboard", "base_url", tb_url)
    parser.set("thingsboard", "mqtt_uri", tb_mqtt_uri)
    parser.set("thingsboard", "provision_url", tb_provision_url)
    parser.set("thingsboard", "provisioning_key", env.get("TB_PROVISIONING_KEY", parser.get("thingsboard", "provisioning_key", fallback="YOUR_TB_PROVISIONING_KEY")))
    parser.set("thingsboard", "provisioning_secret", env.get("TB_PROVISIONING_SECRET", parser.get("thingsboard", "provisioning_secret", fallback="YOUR_TB_PROVISIONING_SECRET")))

    parser.set("device_defaults", "camera_id", env.get("ESP_CAMERA_ID", parser.get("device_defaults", "camera_id", fallback="1")))
    parser.set("device_defaults", "location", env.get("ESP_DEVICE_LOCATION", parser.get("device_defaults", "location", fallback="Chua xac dinh")))
    parser.set("advanced_settings", "wifi_verify_url", f"{api_url}/health")

    parser.set("network", "wifi_sta_static_ip", to_esp_ip_macro(env.get("ESP_STATIC_IP", ""), parser.get("network", "wifi_sta_static_ip", fallback="ESP_IP4TOADDR(192, 168, 1, 8)")))
    parser.set("network", "wifi_sta_static_netmask", to_esp_ip_macro(env.get("ESP_STATIC_NETMASK", ""), parser.get("network", "wifi_sta_static_netmask", fallback="ESP_IP4TOADDR(255, 255, 255, 0)")))
    parser.set("network", "wifi_sta_static_gateway", to_esp_ip_macro(env.get("ESP_STATIC_GATEWAY", ""), parser.get("network", "wifi_sta_static_gateway", fallback="ESP_IP4TOADDR(192, 168, 1, 1)")))

    with PLATFORMIO_PATH.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def main() -> int:
    if not BACKEND_ENV_PATH.exists():
        print(f"Missing backend env file: {BACKEND_ENV_PATH}")
        return 1

    env = parse_env_file(BACKEND_ENV_PATH)
    api_url = resolve_public_api_url(env)
    frontend_api_mode = env.get("FRONTEND_API_MODE", "direct").strip().lower() or "direct"
    write_frontend_env(api_url, frontend_api_mode)
    write_platformio_ini(env, api_url)
    print(f"Synced frontend env -> {FRONTEND_ENV_PATH}")
    print(f"Synced esp32 platformio -> {PLATFORMIO_PATH}")
    print(f"Shared LOCAL_LAN_IP -> {resolve_local_lan_ip(env) or '(not set)'}")
    print(f"Shared PUBLIC_API_URL -> {api_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
