"""
database/models.py — Enums dùng chung toàn backend
Đây là enums duy nhất — KHÔNG tạo thêm enums ở chỗ khác.
Pydantic schemas cho API đặt ở models/ (camera.py, violation.py, zone.py).
"""
from enum import Enum


class TrafficLightState(str, Enum):
    RED    = "red"
    YELLOW = "yellow"
    GREEN  = "green"
    OFF    = "off"


class ViolationType(str, Enum):
    RED_LIGHT   = "red_light"    # Đúng với CHECK constraint trong schema.sql
    SPEEDING    = "speeding"
    WRONG_LANE  = "wrong_lane"
