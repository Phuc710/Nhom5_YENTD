from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

import models
import schemas

OFFLINE_TIMEOUT_SECONDS = 10


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts() -> int:
    return int(time.time())


def _iso_now() -> str:
    return _now_utc().isoformat()


def _to_iso_or_now(value: Optional[str]) -> str:
    if not value:
        return _iso_now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return _iso_now()


def _to_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _to_ts(value: Optional[str]) -> Optional[int]:
    dt = _to_dt(value)
    if not dt:
        return None
    return int(dt.timestamp())


def _relative_last_seen(value: Optional[str]) -> str:
    ts = _to_ts(value)
    if ts is None:
        return "--"
    delta = max(0, _now_ts() - ts)
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    return f"{delta // 3600}h"


def _normalize_status(value: Optional[str], fallback: str = "online") -> str:
    raw = str(value or fallback).strip().lower()
    if raw in {"online", "offline", "degraded", "maintenance"}:
        return raw
    if raw in {"up", "live", "ok", "healthy"}:
        return "online"
    if raw in {"down", "dead", "lost"}:
        return "offline"
    return fallback


def _camera_status_upper(status: Optional[str]) -> str:
    return "ONLINE" if str(status or "").lower() == "online" else "OFFLINE"


def _serialize_payload(payload: object) -> Optional[str]:
    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=True)
    except Exception:
        return str(payload)


def _camera_id_candidates(camera_id: str) -> list[str]:
    cid = (camera_id or "").strip()
    if not cid:
        return []
    out = [cid]
    digits = "".join(ch for ch in cid if ch.isdigit())
    if digits:
        out.extend([
            f"CAM_{int(digits):02d}",
            f"CAM-HCM-{int(digits):03d}",
            f"HCM-S1-A1-CAM-{int(digits):03d}",
            f"esp32_cam_{int(digits)}",
            f"ESP32_CAM_{int(digits)}",
        ])
    return list(dict.fromkeys(out))


# ---- Auth ----
def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or int(user.is_active or 0) != 1:
        return None
    try:
        if check_password_hash(user.password_hash, password):
            return user
    except Exception:
        pass
    return None


# ---- Camera helpers ----
def apply_camera_offline_timeout(db: Session, threshold_seconds: int = OFFLINE_TIMEOUT_SECONDS) -> int:
    cutoff = _now_utc() - timedelta(seconds=max(1, int(threshold_seconds)))
    changed = 0
    cameras = db.query(models.Camera).all()
    for cam in cameras:
        last = _to_dt(cam.last_seen)
        should_offline = (last is None) or (last < cutoff)
        current = str(cam.status or "offline").lower()
        if should_offline and current != "offline":
            cam.status = "offline"
            cam.updated_at = _iso_now()
            changed += 1
    if changed:
        db.commit()
    return changed


def _camera_to_dict(camera: models.Camera) -> dict:
    status_upper = _camera_status_upper(camera.status)
    return {
        "id": camera.id,
        "camera_code": camera.camera_code,
        "camera_id": camera.camera_code,
        "camera_name": camera.camera_name,
        "stream_url": camera.stream_url,
        "location_name": camera.location_name,
        "region_name": camera.location_name,
        "address": camera.location_name,
        "latitude": camera.latitude,
        "longitude": camera.longitude,
        "lat": camera.latitude,
        "lng": camera.longitude,
        "install_position": camera.install_position,
        "direction": camera.install_position,
        "status": status_upper,
        "device_status": status_upper,
        "last_seen": camera.last_seen,
        "last_seen_at": camera.last_seen,
        "last_seen_ts": _to_ts(camera.last_seen),
        "last_seen_str": _relative_last_seen(camera.last_seen),
        "device_model": camera.device_model,
        "ip_address": camera.ip_address,
        "is_active": int(camera.is_active or 0),
        "created_at": camera.created_at,
        "updated_at": camera.updated_at,
    }


def list_cameras(db: Session) -> list[models.Camera]:
    apply_camera_offline_timeout(db)
    return db.query(models.Camera).order_by(models.Camera.camera_code.asc()).all()


def get_camera(db: Session, camera_code: str) -> Optional[models.Camera]:
    apply_camera_offline_timeout(db)
    code = (camera_code or "").strip()
    if not code:
        return None
    q = db.query(models.Camera)
    cam = q.filter(func.lower(models.Camera.camera_code) == code.lower()).first()
    if cam:
        return cam
    if code.isdigit():
        return q.filter(models.Camera.id == int(code)).first()
    for candidate in _camera_id_candidates(code):
        cam = q.filter(func.lower(models.Camera.camera_code) == candidate.lower()).first()
        if cam:
            return cam
    return None


def create_camera(db: Session, payload: schemas.CameraCreate) -> models.Camera:
    now = _iso_now()
    code = (payload.camera_code or "").strip()
    obj = models.Camera(
        camera_code=code,
        camera_name=payload.camera_name,
        stream_url=payload.stream_url,
        location_name=payload.location_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        install_position=payload.install_position,
        status=_normalize_status(payload.status, "offline"),
        last_seen=payload.last_seen,
        device_model=payload.device_model,
        ip_address=payload.ip_address,
        is_active=int(payload.is_active),
        created_at=now,
        updated_at=now,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_camera(db: Session, camera: models.Camera, payload: schemas.CameraUpdate) -> models.Camera:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "status" and value is not None:
            setattr(camera, key, _normalize_status(value, "offline"))
        else:
            setattr(camera, key, value)
    camera.updated_at = _iso_now()
    db.commit()
    db.refresh(camera)
    return camera


def delete_camera(db: Session, camera: models.Camera) -> None:
    db.delete(camera)
    db.commit()


# ---- Violation CRUD ----
def list_violations(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    camera_id: Optional[str] = None,
    plate_number: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[models.Violation]:
    q = db.query(models.Violation)
    if camera_id:
        cam = get_camera(db, camera_id)
        if not cam:
            return []
        q = q.filter(models.Violation.camera_id == cam.id)
    if plate_number:
        plate_q = f"%{str(plate_number).strip().upper()}%"
        q = q.filter(
            func.upper(func.coalesce(models.Violation.plate_number, "")).like(plate_q)
            | func.upper(func.coalesce(models.Violation.normalized_plate_number, "")).like(plate_q)
        )
    if status:
        q = q.filter(func.lower(func.coalesce(models.Violation.status, "")) == str(status).strip().lower())
    if date_from:
        from_iso = _to_iso_or_now(date_from)
        q = q.filter(models.Violation.violation_time >= from_iso)
    if date_to:
        to_iso = _to_iso_or_now(date_to)
        q = q.filter(models.Violation.violation_time <= to_iso)
    return q.order_by(desc(models.Violation.violation_time), desc(models.Violation.id)).offset(offset).limit(limit).all()


def count_violations(
    db: Session,
    *,
    camera_id: Optional[str] = None,
    plate_number: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    q = db.query(func.count(models.Violation.id))
    if camera_id:
        cam = get_camera(db, camera_id)
        if not cam:
            return 0
        q = q.filter(models.Violation.camera_id == cam.id)
    if plate_number:
        plate_q = f"%{str(plate_number).strip().upper()}%"
        q = q.filter(
            func.upper(func.coalesce(models.Violation.plate_number, "")).like(plate_q)
            | func.upper(func.coalesce(models.Violation.normalized_plate_number, "")).like(plate_q)
        )
    if status:
        q = q.filter(func.lower(func.coalesce(models.Violation.status, "")) == str(status).strip().lower())
    if date_from:
        from_iso = _to_iso_or_now(date_from)
        q = q.filter(models.Violation.violation_time >= from_iso)
    if date_to:
        to_iso = _to_iso_or_now(date_to)
        q = q.filter(models.Violation.violation_time <= to_iso)
    return int(q.scalar() or 0)


def get_violation(db: Session, violation_id: int) -> Optional[models.Violation]:
    return db.query(models.Violation).filter(models.Violation.id == violation_id).first()


def create_violation(db: Session, payload: schemas.ViolationCreate) -> models.Violation:
    now = _iso_now()
    data = payload.model_dump(exclude_unset=True)

    camera_pk = data.get("camera_id")
    if not camera_pk and data.get("camera_code"):
        cam = get_camera(db, str(data["camera_code"]))
        camera_pk = cam.id if cam else None
    if not camera_pk:
        first_cam = db.query(models.Camera).order_by(models.Camera.id.asc()).first()
        if not first_cam:
            raise ValueError("No camera available")
        camera_pk = first_cam.id

    vio_time = _to_iso_or_now(data.get("violation_time"))
    violation_code = data.get("violation_code") or f"VIO-{_now_ts()}-{int(time.time_ns() % 1000):03d}"

    obj = models.Violation(
        violation_code=violation_code,
        camera_id=int(camera_pk),
        plate_number=data.get("plate_number"),
        normalized_plate_number=data.get("normalized_plate_number"),
        violation_type=data.get("violation_type") or "red_light_crossing",
        violation_time=vio_time,
        location_snapshot=data.get("location_snapshot"),
        full_image_url=data.get("full_image_url"),
        vehicle_crop_url=data.get("vehicle_crop_url"),
        plate_crop_url=data.get("plate_crop_url"),
        stop_line_snapshot_url=data.get("stop_line_snapshot_url"),
        light_state=data.get("light_state"),
        ocr_text_raw=data.get("ocr_text_raw"),
        ocr_confidence=data.get("ocr_confidence"),
        vehicle_type=data.get("vehicle_type"),
        status=str(data.get("status") or "new").lower(),
        created_at=now,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def _violation_to_dict(db: Session, v: models.Violation) -> dict:
    cam = db.query(models.Camera).filter(models.Camera.id == v.camera_id).first()
    camera_code = cam.camera_code if cam else str(v.camera_id)
    camera_name = cam.camera_name if cam else camera_code
    ts = _to_ts(v.violation_time)
    return {
        "id": v.id,
        "violation_code": v.violation_code,
        "camera_id": camera_code,
        "camera_name": camera_name,
        "camera_pk": v.camera_id,
        "cam": camera_code,
        "plate": v.plate_number,
        "plate_text": v.plate_number,
        "plate_number": v.plate_number,
        "normalized_plate_number": v.normalized_plate_number,
        "violation_type": v.violation_type,
        "violation_time": v.violation_time,
        "violation_ts": ts,
        "location_snapshot": v.location_snapshot,
        "image_url": v.full_image_url,
        "full_image_url": v.full_image_url,
        "vehicle_crop_url": v.vehicle_crop_url,
        "plate_image_url": v.plate_crop_url,
        "plate_crop_url": v.plate_crop_url,
        "stop_line_snapshot_url": v.stop_line_snapshot_url,
        "light_state": v.light_state,
        "ocr_text_raw": v.ocr_text_raw,
        "ocr_confidence": v.ocr_confidence,
        "vehicle_type": v.vehicle_type,
        "status": str(v.status or "new").upper(),
        "created_at": v.created_at,
    }


# ---- Device heartbeat & status ----
def _resolve_camera_from_heartbeat(db: Session, payload: schemas.DeviceHeartbeatIn) -> Optional[models.Camera]:
    if payload.camera_code:
        cam = get_camera(db, payload.camera_code)
        if cam:
            return cam
    if payload.camera_id is not None:
        raw = str(payload.camera_id).strip()
        if raw.isdigit():
            cam = db.query(models.Camera).filter(models.Camera.id == int(raw)).first()
            if cam:
                return cam
        cam = get_camera(db, raw)
        if cam:
            return cam
    return None


def save_device_heartbeat(db: Session, payload: schemas.DeviceHeartbeatIn) -> tuple[models.DeviceHeartbeat, models.Camera]:
    camera = _resolve_camera_from_heartbeat(db, payload)
    if camera is None:
        raise ValueError("Camera not found from heartbeat")

    seen_iso = _to_iso_or_now(payload.last_seen)
    status = _normalize_status(payload.status, "online")
    now_iso = _iso_now()

    heartbeat = models.DeviceHeartbeat(
        camera_id=camera.id,
        status=status,
        latency_ms=payload.latency_ms,
        temperature=payload.temperature,
        signal_strength=payload.signal_strength,
        payload=_serialize_payload(payload.payload),
        created_at=seen_iso,
    )
    db.add(heartbeat)

    camera.last_seen = seen_iso
    camera.status = "online"
    if payload.ip_address:
        camera.ip_address = payload.ip_address
    camera.updated_at = now_iso

    db.commit()
    db.refresh(heartbeat)
    db.refresh(camera)
    return heartbeat, camera


def list_devices_map(db: Session) -> dict[str, dict]:
    apply_camera_offline_timeout(db)
    out: dict[str, dict] = {}
    cameras = db.query(models.Camera).order_by(models.Camera.camera_code.asc()).all()
    for cam in cameras:
        last_hb = (
            db.query(models.DeviceHeartbeat)
            .filter(models.DeviceHeartbeat.camera_id == cam.id)
            .order_by(desc(models.DeviceHeartbeat.created_at), desc(models.DeviceHeartbeat.id))
            .first()
        )
        ts = _to_ts(cam.last_seen)
        status_upper = _camera_status_upper(cam.status)
        key = cam.camera_code
        out[key] = {
            "camera_id": cam.camera_code,
            "device_id": cam.camera_code,
            "device_name": cam.camera_name,
            "device_type": "CAMERA",
            "status": status_upper,
            "last_seen": ts,
            "last_seen_str": _relative_last_seen(cam.last_seen),
            "last_heartbeat_ts": ts,
            "signal": last_hb.signal_strength if last_hb else None,
            "signal_strength": last_hb.signal_strength if last_hb else None,
            "temp": last_hb.temperature if last_hb else None,
            "latency_ms": last_hb.latency_ms if last_hb else None,
            "ip_address": cam.ip_address,
        }
    return out


def camera_status(db: Session, camera_id: str) -> schemas.CameraStatusOut:
    cam = get_camera(db, camera_id)
    if not cam:
        raise ValueError("Camera not found")

    last_violation = (
        db.query(models.Violation)
        .filter(models.Violation.camera_id == cam.id)
        .order_by(desc(models.Violation.violation_time), desc(models.Violation.id))
        .first()
    )

    status_upper = _camera_status_upper(cam.status)
    return schemas.CameraStatusOut(
        camera_id=cam.camera_code,
        online=status_upper == "ONLINE",
        status=status_upper,
        last_seen=cam.last_seen,
        last_seen_at=cam.last_seen,
        last_violation_id=last_violation.id if last_violation else None,
    )


# ---- Dashboard bootstrap ----
def bootstrap_payload(db: Session) -> dict:
    apply_camera_offline_timeout(db)
    cameras = [_camera_to_dict(c) for c in db.query(models.Camera).order_by(models.Camera.camera_code.asc()).all()]
    violations = [_violation_to_dict(db, v) for v in list_violations(db, limit=20)]
    devices = list_devices_map(db)

    total = db.query(func.count(models.Violation.id)).scalar() or 0
    today = db.query(func.count(models.Violation.id)).filter(models.Violation.status != "deleted").scalar() or 0

    return {
        "ok": True,
        "cameras": cameras,
        "violations": violations,
        "data": violations,
        "devices": devices,
        "stats": {
            "violations_total": int(total),
            "violations_today": int(today),
            "ai_detections": int(total),
        },
        "traffic": {
            "light": "RED",
            "mode": "AUTO",
            "countdown": 0,
            "camera": "ACTIVE",
        },
        "context": {},
        "runtime_source": {
            "enabled": False,
            "active": False,
            "mode": "backend",
            "source": "backend",
            "status": "active",
            "fallback_active": False,
            "label": "Backend API",
            "index": 0,
        },
    }


def camera_to_public_dict(camera: models.Camera) -> dict:
    return _camera_to_dict(camera)


def violation_to_public_dict(db: Session, violation: models.Violation) -> dict:
    return _violation_to_dict(db, violation)
