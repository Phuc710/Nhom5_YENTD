"""
config/settings.py — OOP Settings từ .env
Dùng pydantic-settings để validate tất cả environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


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

    # Uploads
    upload_dir: str = "uploads"
    max_upload_size: int = 10_485_760  # 10MB

    # ML Models
    detector_model_path: str = "ml/LP_detector_nano_61.pt"
    ocr_model_path: str = "ml/LP_ocr_nano_62.pt"
    confidence_threshold: float = 0.5
    iou_threshold: float = 0.45

    # Violation processing
    dedup_time_window: int = 30        # seconds — bỏ qua vi phạm trùng trong 30s
    quality_threshold: float = 70.0    # điểm chất lượng ảnh tối thiểu (0-100)
    min_vote_count: int = 1            # số vote tối thiểu để xác nhận biển số
    buffer_window_seconds: int = 10    # giữ frame trong buffer bao lâu
    buffer_min_frames: int = 3         # số frame tối thiểu để process
    buffer_timeout_seconds: int = 3    # timeout nếu không có frame mới

    # Timezone
    timezone: str = "Asia/Ho_Chi_Minh"

    # CORS
    cors_origins: str = "http://localhost:8080"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Backward compat singleton (used by old services)
settings = get_settings()
