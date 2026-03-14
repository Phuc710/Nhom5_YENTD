"""Cấu hình backend từ biến môi trường."""

from functools import lru_cache
from typing import Any, List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings
import os


DEFAULT_CORS_ORIGINS = ",".join([
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:80",
    "http://127.0.0.1:80",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
])


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_service_key: str = ""

    # ThingsBoard
    thingsboard_url: str = "http://localhost:9090"
    thingsboard_username: str = "tenant@thingsboard.org"
    thingsboard_password: str = "tenant"

    # MQTT ThingsBoard broker
    mqtt_tb_host: str = "localhost"
    mqtt_tb_port: int = 1883

    # MQTT Mosquitto broker
    mqtt_host: str = "localhost"
    mqtt_port: int = 1888

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    public_api_url: str = ""

    # Uploads
    upload_dir: str = "uploads"
    max_upload_size: int = 10_485_760

    # ML Models
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

    # Violation processing
    dedup_time_window: int = 30
    quality_threshold: float = 75.0
    min_vote_count: int = 2
    vote_confidence_threshold: float = 0.75
    vote_fuzzy_distance: int = 1
    buffer_window_seconds: int = 120
    buffer_min_frames: int = 3
    buffer_timeout_seconds: int = 3

    # Timezone
    timezone: str = "Asia/Ho_Chi_Minh"

    # CORS
    cors_origins: str = DEFAULT_CORS_ORIGINS

    # ThingsBoard sync
    thingsboard_sync_enabled: bool = True
    thingsboard_sync_interval_seconds: int = 30
    thingsboard_sync_page_size: int = 100
    thingsboard_device_name_prefix: str = ""

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        """Chuyển các đường dẫn tương đối thành tuyệt đối dựa trên thư mục backend."""
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if not os.path.isabs(self.upload_dir):
            self.upload_dir = os.path.join(base_path, self.upload_dir)
            
        if not os.path.isabs(self.detector_model_path):
            self.detector_model_path = os.path.join(base_path, self.detector_model_path)
            
        if not os.path.isabs(self.ocr_model_path):
            self.ocr_model_path = os.path.join(base_path, self.ocr_model_path)
            
        return self

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: Any) -> bool:
        """Cho phép DEBUG nhận cả bool lẫn mode string như release/debug."""
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

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def supabase_auth_mode(self) -> str:
        return "service_role" if self.supabase_service_key else "anon"

    class Config:
        import os
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(base_path, ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
