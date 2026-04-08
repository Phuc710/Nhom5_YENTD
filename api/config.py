"""
Centralized application configuration using Pydantic Settings.
Reads from environment variables or .env file.

ALL settings in ONE place — server, models, Supabase, MQTT, ThingsBoard.
Override with TRAFFIC_* environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class AppSettings(BaseSettings):
    """
    All configurable parameters for the TrafficCam API.
    Override via environment variables (prefix TRAFFIC_) or a .env file.
    """

    # --- Server ---
    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8000, description="Server port")

    # --- Model weights ---
    vehicle_weight: str = Field(
        default="models/vehicle/vehicle_yolov8s.pt",
        description="Path to vehicle detector YOLO weight",
    )
    plate_weight: str = Field(
        default="models/plate/plate_yolov8n.pt",
        description="Path to plate detector YOLO weight",
    )
    dsort_weight: str = Field(
        default="models/deepsort/ckpt.t7",
        description="Path to DeepSORT weight",
    )

    # --- Detection thresholds ---
    vconf: float = Field(default=0.6, ge=0.0, le=1.0, description="Vehicle detection confidence")
    pconf: float = Field(default=0.25, ge=0.0, le=1.0, description="Plate detection confidence")
    ocr_thres: float = Field(default=0.9, ge=0.0, le=1.0, description="OCR confidence threshold")

    # --- Features ---
    read_plate: bool = Field(default=True, description="Enable license plate OCR")
    deepsort: bool = Field(default=False, description="Use DeepSORT instead of SORT")
    device: str = Field(default="0", description="CUDA device id or 'cpu'")
    lang: str = Field(default="en", description="Display language (vi, en, es, fr)")

    # --- Stream defaults ---
    stream_reconnect_delay: float = Field(
        default=2.0, description="Seconds to wait before reconnecting a dropped stream"
    )
    stream_max_fps: int = Field(
        default=30, description="Max FPS cap for MJPEG output stream"
    )

    # --- Supabase ---
    supabase_url: str = Field(
        default="", description="Supabase project URL (e.g. https://xxx.supabase.co)"
    )
    supabase_key: str = Field(
        default="", description="Supabase service_role key for write access"
    )

    # --- MQTT ---
    mqtt_enabled: bool = Field(default=False, description="Enable MQTT client")
    mqtt_broker_host: str = Field(default="thingsboard.cloud", description="MQTT broker host")
    mqtt_broker_port: int = Field(default=1883, description="MQTT broker port")
    mqtt_client_id: str = Field(default="trafficcam-backend", description="MQTT client ID")
    mqtt_username: str = Field(default="", description="MQTT username (ThingsBoard access token)")
    mqtt_password: str = Field(default="", description="MQTT password")

    # --- ThingsBoard ---
    tb_host: str = Field(default="thingsboard.cloud", description="ThingsBoard host")
    tb_access_token: str = Field(default="", description="ThingsBoard device access token")

    model_config = {
        "env_prefix": "TRAFFIC_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # --- Computed helpers ---

    @property
    def supabase_configured(self) -> bool:
        """Check if Supabase credentials are configured."""
        return bool(self.supabase_url and self.supabase_key)

    @property
    def mqtt_configured(self) -> bool:
        """Check if MQTT is enabled and configured."""
        return bool(self.mqtt_enabled and self.mqtt_broker_host)


# Singleton instance — imported everywhere
settings = AppSettings()
