"""
Dependency injection — singleton instances shared across the application.
"""
from api.services.alpr_service import ALPRService
from api.services.stream_manager import StreamManager
from api.services.db_service import DBService
from api.services.mqtt_service import MQTTService
from api.services.local_settings_service import LocalSettingsService, local_settings as _local_settings_instance
from api.services.image_service import ImageService

# Singleton instances
alpr_service = ALPRService()
stream_manager = StreamManager()
db_service = DBService()
mqtt_service = MQTTService()
local_settings = _local_settings_instance
image_service = ImageService()


def get_alpr_service() -> ALPRService:
    """FastAPI dependency for ALPRService."""
    return alpr_service


def get_stream_manager() -> StreamManager:
    """FastAPI dependency for StreamManager."""
    return stream_manager


def get_db_service() -> DBService:
    """FastAPI dependency for DBService (Supabase)."""
    return db_service


def get_mqtt_service() -> MQTTService:
    """FastAPI dependency for MQTTService."""
    return mqtt_service


def get_local_settings() -> LocalSettingsService:
    """FastAPI dependency for LocalSettingsService."""
    return local_settings


def get_image_service() -> ImageService:
    """FastAPI dependency for ImageService (WebP compress + Supabase upload)."""
    return image_service
