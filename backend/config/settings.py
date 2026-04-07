"""Backend settings loaded from environment variables."""

from functools import lru_cache
import os
from typing import Any, List
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


LOCALHOST_CORS_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:80",
    "http://127.0.0.1:80",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]


def build_default_cors_origins(local_lan_ip: str = "") -> str:
    origins = list(LOCALHOST_CORS_ORIGINS)
    lan_ip = (local_lan_ip or "").strip()
    if lan_ip:
        origins.extend([
            f"http://{lan_ip}",
            f"http://{lan_ip}:8080",
        ])
    return ",".join(origins)


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_service_key: str = ""

    # Shared local LAN source of truth
    local_lan_ip: str = ""

    # ThingsBoard
    thingsboard_url: str = ""
    thingsboard_username: str = "tenant@thingsboard.org"
    thingsboard_password: str = "tenant"

    # MQTT ThingsBoard broker
    mqtt_tb_host: str = ""
    mqtt_tb_port: int = 1883

    # MQTT Mosquitto broker
    mqtt_host: str = ""
    mqtt_port: int = 1888

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    hot_reload: bool = False
    log_level: str = "INFO"
    public_api_url: str = ""
    enable_stream_workers: bool = True
    stream_workers_start_on_startup: bool = False
    stream_capture_mode: str = "mjpeg"
    stream_snapshot_interval_ms: int = 800

    # Uploads
    upload_dir: str = "uploads"
    max_upload_size: int = 10_485_760

    # Supabase Storage
    supabase_storage_bucket: str = "Camera AI"
    storage_upload_enabled: bool = True

    # ML Models
    ml_enabled: bool = True              # False = tắt toàn bộ AI, chỉ stream
    detector_model_path: str = "ml/LP_detector_nano_61.pt"
    ocr_model_path: str = "ml/LP_ocr_nano_62.pt"
    confidence_threshold: float = 0.5
    iou_threshold: float = 0.45
    ml_device: str = "auto"
    ml_use_half: bool = True
    ml_detector_imgsz: int = 640
    ml_ocr_imgsz: int = 320
    ml_max_det: int = 4
    ml_metrics_window: int = 256
    ml_preload_on_startup: bool = True
    ml_warmup_runs: int = 1
    ml_rotate_180: bool = True
    ml_flip_horizontal: bool = True

    # Violation processing
    dedup_time_window: int = 30
    quality_threshold: float = 75.0
    vehicle_crop_pad_x: float = 2.5
    vehicle_crop_pad_top: float = 3.0
    vehicle_crop_pad_bottom: float = 1.5

    # Timezone
    timezone: str = "Asia/Ho_Chi_Minh"
    camera_status_ttl_seconds: int = 10

    # CORS
    cors_origins: str = ""

    thingsboard_sync_page_size: int = 100
    thingsboard_device_name_prefix: str = ""
    thingsboard_auto_sync_on_startup: bool = False
    thingsboard_auto_sync_interval_seconds: int = 0

    @model_validator(mode="after")
    def resolve_settings(self) -> "Settings":
        """Resolve derived URLs, hosts, and relative paths."""
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.local_lan_ip = self.local_lan_ip.strip()
        fallback_host = self.local_lan_ip or "localhost"

        if not self.thingsboard_url.strip():
            self.thingsboard_url = f"http://{fallback_host}:9090"
        self.thingsboard_url = self.thingsboard_url.strip().rstrip("/")

        if not self.mqtt_tb_host.strip():
            parsed_tb_url = urlparse(self.thingsboard_url)
            self.mqtt_tb_host = parsed_tb_url.hostname or fallback_host
        self.mqtt_tb_host = self.mqtt_tb_host.strip()

        if not self.mqtt_host.strip():
            self.mqtt_host = fallback_host
        self.mqtt_host = self.mqtt_host.strip()

        if not self.public_api_url.strip() and self.local_lan_ip:
            self.public_api_url = f"http://{self.local_lan_ip}:{self.port}"
        self.public_api_url = self.public_api_url.strip().rstrip("/")

        if not self.cors_origins.strip():
            self.cors_origins = build_default_cors_origins(self.local_lan_ip)

        if not os.path.isabs(self.upload_dir):
            self.upload_dir = os.path.join(base_path, self.upload_dir)

        if not os.path.isabs(self.detector_model_path):
            self.detector_model_path = os.path.join(base_path, self.detector_model_path)

        if not os.path.isabs(self.ocr_model_path):
            self.ocr_model_path = os.path.join(base_path, self.ocr_model_path)

        self.stream_capture_mode = (self.stream_capture_mode or "snapshot").strip().lower()
        if self.stream_capture_mode not in {"snapshot", "mjpeg"}:
            self.stream_capture_mode = "snapshot"

        if self.stream_snapshot_interval_ms < 200:
            self.stream_snapshot_interval_ms = 200

        return self

    @field_validator("debug", "enable_stream_workers", "stream_workers_start_on_startup", mode="before")
    @classmethod
    def normalize_bool(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value

        if value is None:
            return False

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "dev", "development"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return bool(value)

    @field_validator(
        "local_lan_ip",
        "thingsboard_url",
        "mqtt_tb_host",
        "mqtt_host",
        "cors_origins",
        mode="before",
    )
    @classmethod
    def normalize_string_value(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("public_api_url", mode="before")
    @classmethod
    def normalize_public_api_url(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().rstrip("/")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def supabase_auth_mode(self) -> str:
        return "service_role" if self.supabase_service_key else "anon"

    class Config:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(base_path, ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
