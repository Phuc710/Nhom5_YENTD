from __future__ import annotations

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_code = Column(String, unique=True, nullable=False, index=True)
    camera_name = Column(String, nullable=False)
    stream_url = Column(String, nullable=False, default="")
    location_name = Column(String, nullable=False, default="")
    latitude = Column(Float)
    longitude = Column(Float)
    install_position = Column(String)
    status = Column(String, nullable=False, default="offline", index=True)
    last_seen = Column(String)
    device_model = Column(String)
    ip_address = Column(String)
    is_active = Column(Integer, nullable=False, default=1, index=True)
    created_at = Column(String)
    updated_at = Column(String)

    heartbeats = relationship("DeviceHeartbeat", back_populates="camera")


class Violation(Base):
    __tablename__ = "violations"

    id = Column(Integer, primary_key=True, index=True)
    violation_code = Column(String, unique=True, nullable=False, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    plate_number = Column(String)
    normalized_plate_number = Column(String, index=True)
    violation_type = Column(String, nullable=False)
    violation_time = Column(String, nullable=False, index=True)
    location_snapshot = Column(String)
    full_image_url = Column(String)
    vehicle_crop_url = Column(String)
    plate_crop_url = Column(String)
    stop_line_snapshot_url = Column(String)
    light_state = Column(String)
    ocr_text_raw = Column(Text)
    ocr_confidence = Column(Float)
    vehicle_type = Column(String)
    status = Column(String, nullable=False, default="new", index=True)
    created_at = Column(String)


class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeats"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    latency_ms = Column(Integer)
    temperature = Column(Float)
    signal_strength = Column(Integer)
    payload = Column(Text)
    created_at = Column(String, nullable=False, index=True)

    camera = relationship("Camera", back_populates="heartbeats")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="operator")
    is_active = Column(Integer, default=1)
    created_at = Column(String)
