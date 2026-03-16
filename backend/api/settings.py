import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config.settings import get_settings

router = APIRouter(prefix="/settings", tags=["Settings"])

class SystemSettingsUpdate(BaseModel):
    mqtt_host: str = None
    mqtt_port: int = None
    ai_confidence_threshold: float = None
    retention_days: int = None


@router.get("/system")
async def get_system_settings():
    s = get_settings()
    return {
        "mqtt_host": s.mqtt_tb_host,
        "mqtt_port": s.mqtt_tb_port,
        "ai_confidence_threshold": s.confidence_threshold,
        "retention_days": s.dedup_time_window, # Mocking retention for now
    }


@router.put("/system")
async def update_system_settings(data: SystemSettingsUpdate):
    """
    Updates the .env file with new configuration parameters.
    In a true production environment, you would use a database or a config manager.
    Here we rewrite the .env file for persistence.
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    
    if not os.path.exists(env_path):
        raise HTTPException(status_code=404, detail=".env file not found")

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updates = {
        "MQTT_TB_HOST": str(data.mqtt_host) if data.mqtt_host is not None else None,
        "MQTT_TB_PORT": str(data.mqtt_port) if data.mqtt_port is not None else None,
        "CONFIDENCE_THRESHOLD": str(data.ai_confidence_threshold) if data.ai_confidence_threshold is not None else None,
        "DEDUP_TIME_WINDOW": str(data.retention_days) if data.retention_days is not None else None,
    }

    new_lines = []
    updated_keys = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
            
        key = stripped.split("=")[0]
        if key in updates and updates[key] is not None:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append new keys if they didn't exist
    for key, val in updates.items():
        if val is not None and key not in updated_keys:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Note: Requires a backend restart to take effect fully, 
    # but we return success so the frontend knows the config was saved.
    return {"message": "Settings updated successfully"}
