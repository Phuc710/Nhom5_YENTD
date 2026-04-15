from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

import crud
import schemas
from database import Base, DATABASE_URL, SessionLocal, engine, ensure_sqlite_compat_schema, get_db

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover
    mqtt = None

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent
FRONTEND_DIR = REPO_DIR / "DEVELOPER"
IMAGE_DIR = REPO_DIR / "imge"
LEGACY_IMAGE_DIR = BASE_DIR / "imge"

for p in (IMAGE_DIR, LEGACY_IMAGE_DIR):
    p.mkdir(parents=True, exist_ok=True)

ensure_sqlite_compat_schema()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="TrafficAI Backend", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DASHBOARD_SECRET = (os.getenv("DASHBOARD_SECRET") or "TRAFFIC_AI_TOKEN").strip()

MQTT_ENABLED = (os.getenv("MQTT_ENABLED") or "1").strip().lower() in {"1", "true", "yes", "on"}
MQTT_HOST = (os.getenv("MQTT_HOST") or "127.0.0.1").strip()
MQTT_PORT = int((os.getenv("MQTT_PORT") or "1883").strip())
MQTT_USERNAME = (os.getenv("MQTT_USERNAME") or "").strip()
MQTT_PASSWORD = (os.getenv("MQTT_PASSWORD") or "").strip()
MQTT_TOPIC_PREFIX = (os.getenv("MQTT_TOPIC_PREFIX") or "traffic").strip().strip("/")

_sse_lock = threading.Lock()
_sse_subscribers: set[queue.Queue] = set()
_mqtt_client: Optional["mqtt.Client"] = None
_mqtt_connected = False
_mqtt_last_error: Optional[str] = None
_status_worker_thread: Optional[threading.Thread] = None
_status_worker_stop = threading.Event()
_camera_status_cache: dict[str, str] = {}
log = logging.getLogger("traffic-backend")


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    raw = authorization.strip()
    prefix = "bearer "
    if raw.lower().startswith(prefix):
        return raw[len(prefix) :].strip()
    return None


def require_token(authorization: Optional[str] = Header(default=None)) -> str:
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    if token != DASHBOARD_SECRET:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token


def require_token_or_query(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> str:
    header_token = _extract_bearer(authorization)
    query_token = (token or "").strip()
    resolved = header_token or query_token
    if not resolved:
        raise HTTPException(status_code=401, detail="Missing token")
    if resolved != DASHBOARD_SECRET:
        raise HTTPException(status_code=401, detail="Invalid token")
    return resolved


def _publish_realtime(event_type: str, topic: str, payload: dict) -> None:
    data = {
        "type": event_type,
        "topic": topic,
        "ts": int(time.time()),
        "payload": payload,
    }
    with _sse_lock:
        subscribers = list(_sse_subscribers)
    for q in subscribers:
        try:
            q.put_nowait(data)
        except queue.Full:
            pass


def _find_camera_code_from_topic(topic: str) -> Optional[str]:
    # Expected:
    # traffic/camera/{camera_code}/status
    # traffic/camera/{camera_code}/heartbeat
    # traffic/camera/{camera_code}/violation
    parts = [p for p in topic.split("/") if p]
    if len(parts) >= 4 and parts[0] == MQTT_TOPIC_PREFIX and parts[1] == "camera":
        return parts[2]
    return None


def _normalize_event_status(value: object) -> str:
    raw = str(value or "online").strip().lower()
    if raw in {"online", "offline", "degraded", "maintenance"}:
        return raw
    if raw in {"up", "live", "ok", "healthy"}:
        return "online"
    if raw in {"down", "lost", "dead"}:
        return "offline"
    return "online"


def _handle_mqtt_heartbeat_or_status(topic: str, payload: dict) -> None:
    camera_code = payload.get("camera_code") or _find_camera_code_from_topic(topic)
    if not camera_code:
        return
    status = _normalize_event_status(payload.get("status"))
    hb_payload = {
        "camera_code": str(camera_code),
        "status": status,
        "latency_ms": payload.get("latency_ms"),
        "temperature": payload.get("temperature"),
        "signal_strength": payload.get("signal_strength"),
        "ip_address": payload.get("ip_address"),
        "last_seen": payload.get("last_seen"),
        "payload": payload,
    }
    db = SessionLocal()
    try:
        validated = schemas.DeviceHeartbeatIn(**hb_payload)
        hb, cam = crud.save_device_heartbeat(db, validated)
        if status != "online":
            cam = crud.update_camera(db, cam, schemas.CameraUpdate(status=status, last_seen=hb_payload.get("last_seen")))
        realtime_payload = {
            "id": hb.id,
            "camera_code": cam.camera_code,
            "camera_id": cam.camera_code,
            "status": status.upper(),
            "latency_ms": hb.latency_ms,
            "temperature": hb.temperature,
            "signal_strength": hb.signal_strength,
            "ip_address": cam.ip_address,
            "last_seen": cam.last_seen,
            "last_seen_at": cam.last_seen,
        }
        _publish_realtime("camera_status_updated", topic, realtime_payload)
    except Exception as exc:
        log.warning("MQTT heartbeat processing failed topic=%s err=%s", topic, exc)
    finally:
        db.close()


def _handle_mqtt_violation(topic: str, payload: dict) -> None:
    # Keep realtime relay lightweight for now; DB insertion can remain API-driven.
    _publish_realtime("violation_created", topic, payload)


def _handle_mqtt_system_event(topic: str, payload: dict) -> None:
    _publish_realtime("system_event", topic, payload)


def _on_mqtt_connect(client, userdata, flags, rc):
    global _mqtt_connected
    _mqtt_connected = rc == 0
    if rc != 0:
        return
    topics = [
        (f"{MQTT_TOPIC_PREFIX}/camera/+/status", 0),
        (f"{MQTT_TOPIC_PREFIX}/camera/+/heartbeat", 0),
        (f"{MQTT_TOPIC_PREFIX}/camera/+/violation", 0),
        (f"{MQTT_TOPIC_PREFIX}/system/events", 0),
    ]
    for topic, qos in topics:
        client.subscribe(topic, qos=qos)


def _on_mqtt_disconnect(client, userdata, rc):
    global _mqtt_connected
    _mqtt_connected = False


def _on_mqtt_message(client, userdata, msg):
    try:
        payload_raw = msg.payload.decode("utf-8", errors="ignore") if isinstance(msg.payload, (bytes, bytearray)) else str(msg.payload)
        payload = json.loads(payload_raw) if payload_raw else {}
    except Exception:
        payload = {"raw": payload_raw if "payload_raw" in locals() else ""}
    topic = msg.topic or ""

    if topic.endswith("/heartbeat") or topic.endswith("/status"):
        _handle_mqtt_heartbeat_or_status(topic, payload if isinstance(payload, dict) else {})
    elif topic.endswith("/violation"):
        _handle_mqtt_violation(topic, payload if isinstance(payload, dict) else {"raw": str(payload)})
    elif topic.endswith("/events"):
        _handle_mqtt_system_event(topic, payload if isinstance(payload, dict) else {"raw": str(payload)})


def _start_mqtt_bridge() -> None:
    global _mqtt_client, _mqtt_last_error, _mqtt_connected
    if not MQTT_ENABLED:
        _mqtt_connected = False
        _mqtt_last_error = "MQTT disabled"
        return
    if mqtt is None:
        _mqtt_connected = False
        _mqtt_last_error = "paho-mqtt not installed"
        return

    try:
        client_id = f"traffic-backend-{int(time.time())}"
        client = mqtt.Client(client_id=client_id)
        if MQTT_USERNAME:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.on_connect = _on_mqtt_connect
        client.on_disconnect = _on_mqtt_disconnect
        client.on_message = _on_mqtt_message
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        _mqtt_client = client
        _mqtt_last_error = None
    except Exception as exc:  # pragma: no cover
        _mqtt_connected = False
        _mqtt_last_error = str(exc)


def _stop_mqtt_bridge() -> None:
    global _mqtt_client, _mqtt_connected
    if _mqtt_client is not None:
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        except Exception:
            pass
    _mqtt_client = None
    _mqtt_connected = False


def _camera_status_worker_loop() -> None:
    # Periodically enforce offline timeout and push realtime status transitions.
    while not _status_worker_stop.is_set():
        db = SessionLocal()
        try:
            rows = crud.list_cameras(db)
            current: dict[str, str] = {}
            for cam in rows:
                code = str(cam.camera_code or "")
                if not code:
                    continue
                status_up = "ONLINE" if str(cam.status or "").lower() == "online" else "OFFLINE"
                current[code] = status_up
                prev = _camera_status_cache.get(code)
                if prev is not None and prev != status_up:
                    payload = {
                        "camera_id": code,
                        "camera_code": code,
                        "status": status_up,
                        "last_seen": cam.last_seen,
                        "last_seen_at": cam.last_seen,
                        "ip_address": cam.ip_address,
                    }
                    _publish_realtime("camera_status_updated", f"{MQTT_TOPIC_PREFIX}/camera/{code}/status", payload)
            _camera_status_cache.clear()
            _camera_status_cache.update(current)
        except Exception as exc:
            log.debug("camera status worker error: %s", exc)
        finally:
            db.close()
        _status_worker_stop.wait(timeout=2.0)


def _start_status_worker() -> None:
    global _status_worker_thread
    if _status_worker_thread and _status_worker_thread.is_alive():
        return
    _status_worker_stop.clear()
    _status_worker_thread = threading.Thread(target=_camera_status_worker_loop, daemon=True, name="camera-status-worker")
    _status_worker_thread.start()


def _stop_status_worker() -> None:
    _status_worker_stop.set()


@app.on_event("startup")
def _on_startup() -> None:
    _start_mqtt_bridge()
    _start_status_worker()


@app.on_event("shutdown")
def _on_shutdown() -> None:
    _stop_status_worker()
    _stop_mqtt_bridge()


@app.post("/api/login", response_model=schemas.LoginResponse)
def api_login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return schemas.LoginResponse(ok=True, token=DASHBOARD_SECRET, role=(user.role or "operator").lower())


@app.get("/api/health")
def api_health(db: Session = Depends(get_db)):
    _ = db.execute(text("SELECT 1"))
    return {
        "ok": True,
        "ts": int(time.time()),
        "database": DATABASE_URL,
        "mqtt": {
            "enabled": MQTT_ENABLED,
            "connected": _mqtt_connected,
            "host": MQTT_HOST,
            "port": MQTT_PORT,
            "topic_prefix": MQTT_TOPIC_PREFIX,
            "last_error": _mqtt_last_error,
        },
    }


@app.get("/api/realtime/events")
def api_realtime_events(token: Optional[str] = Query(default=None)):
    if (token or "").strip() != DASHBOARD_SECRET:
        raise HTTPException(status_code=401, detail="Invalid token")

    q: queue.Queue = queue.Queue(maxsize=200)
    with _sse_lock:
        _sse_subscribers.add(q)

    def gen():
        try:
            hello = {"type": "system_event", "topic": f"{MQTT_TOPIC_PREFIX}/system/events", "ts": int(time.time()), "payload": {"event": "connected"}}
            yield f"data: {json.dumps(hello, ensure_ascii=True)}\n\n"
            while True:
                try:
                    item = q.get(timeout=20)
                    yield f"data: {json.dumps(item, ensure_ascii=True)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with _sse_lock:
                _sse_subscribers.discard(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/bootstrap")
def api_bootstrap(db: Session = Depends(get_db), _: str = Depends(require_token)):
    return crud.bootstrap_payload(db)


@app.get("/api/cameras")
def get_cameras(db: Session = Depends(get_db), _: str = Depends(require_token)):
    rows = crud.list_cameras(db)
    return {"ok": True, "cameras": [crud.camera_to_public_dict(c) for c in rows]}


@app.get("/api/cameras/{camera_id}")
def get_camera(camera_id: str, db: Session = Depends(get_db), _: str = Depends(require_token)):
    row = crud.get_camera(db, camera_id)
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"ok": True, "camera": crud.camera_to_public_dict(row)}


@app.get("/api/cameras/{camera_id}/stream")
def get_camera_stream(
    camera_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_token_or_query),
):
    camera = crud.get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    raw_url = str(camera.stream_url or "").strip()
    if not raw_url:
        raise HTTPException(status_code=404, detail="Camera stream_url is empty")

    # If stream url is already a backend-local route, keep frontend on backend origin.
    if raw_url.startswith("/"):
        return RedirectResponse(url=raw_url, status_code=307)

    if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Only http/https MJPEG stream is supported by proxy")

    try:
        upstream = requests.get(raw_url, stream=True, timeout=(5, 30))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cannot connect upstream stream: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Upstream stream returned HTTP {upstream.status_code}")

    content_type = upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame")

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return StreamingResponse(
        generate(),
        media_type=content_type,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/cameras")
def post_camera(payload: schemas.CameraCreate, db: Session = Depends(get_db), _: str = Depends(require_token)):
    camera_code = (payload.camera_code or "").strip()
    if not camera_code:
        raise HTTPException(status_code=422, detail="camera_code (or camera_id) is required")
    exists = crud.get_camera(db, camera_code)
    if exists:
        raise HTTPException(status_code=409, detail="Camera already exists")
    row = crud.create_camera(db, payload)
    return {"ok": True, "camera": crud.camera_to_public_dict(row)}


@app.put("/api/cameras/{camera_id}")
def put_camera(camera_id: str, payload: schemas.CameraUpdate, db: Session = Depends(get_db), _: str = Depends(require_token)):
    row = crud.get_camera(db, camera_id)
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    row = crud.update_camera(db, row, payload)
    return {"ok": True, "camera": crud.camera_to_public_dict(row)}


@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db), _: str = Depends(require_token)):
    row = crud.get_camera(db, camera_id)
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    crud.delete_camera(db, row)
    return {"ok": True}


@app.get("/api/violations")
def get_violations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    plate_number: Optional[str] = None,
    camera_id: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    rows = crud.list_violations(
        db,
        limit=limit,
        offset=offset,
        camera_id=camera_id,
        plate_number=plate_number,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    total = crud.count_violations(
        db,
        camera_id=camera_id,
        plate_number=plate_number,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    data = [crud.violation_to_public_dict(db, v) for v in rows]
    return {"ok": True, "violations": data, "data": data, "total": total, "limit": limit, "offset": offset}


@app.get("/api/violations/{violation_id}")
def get_violation(violation_id: int, db: Session = Depends(get_db), _: str = Depends(require_token)):
    row = crud.get_violation(db, violation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Violation not found")
    return {"ok": True, "violation": crud.violation_to_public_dict(db, row)}


@app.post("/api/violations")
def post_violation(payload: schemas.ViolationCreate, db: Session = Depends(get_db), _: str = Depends(require_token)):
    try:
        row = crud.create_violation(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = crud.violation_to_public_dict(db, row)
    _publish_realtime("violation_created", f"{MQTT_TOPIC_PREFIX}/camera/{out.get('camera_id', 'unknown')}/violation", out)
    return {"ok": True, "violation": out}


@app.get("/api/cameras/{camera_id}/status")
def get_camera_status(camera_id: str, db: Session = Depends(get_db), _: str = Depends(require_token)):
    try:
        status = crud.camera_status(db, camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "status": status.model_dump()}


@app.post("/api/devices/heartbeat")
def post_device_heartbeat(payload: schemas.DeviceHeartbeatIn, db: Session = Depends(get_db), _: str = Depends(require_token)):
    try:
        hb, cam = crud.save_device_heartbeat(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    event_payload = {
        "id": hb.id,
        "camera_id": cam.camera_code,
        "camera_code": cam.camera_code,
        "status": "ONLINE",
        "latency_ms": hb.latency_ms,
        "temperature": hb.temperature,
        "signal_strength": hb.signal_strength,
        "ip_address": cam.ip_address,
        "last_seen": cam.last_seen,
        "last_seen_at": cam.last_seen,
        "created_at": hb.created_at,
    }
    _publish_realtime("camera_status_updated", f"{MQTT_TOPIC_PREFIX}/camera/{cam.camera_code}/heartbeat", event_payload)

    return {
        "ok": True,
        "heartbeat": {
            "id": hb.id,
            "camera_id": cam.id,
            "camera_code": cam.camera_code,
            "status": "ONLINE",
            "latency_ms": hb.latency_ms,
            "temperature": hb.temperature,
            "signal_strength": hb.signal_strength,
            "ip_address": cam.ip_address,
            "created_at": hb.created_at,
        },
        "camera": {
            "id": cam.id,
            "camera_id": cam.camera_code,
            "camera_code": cam.camera_code,
            "status": "ONLINE",
            "device_status": "ONLINE",
            "last_seen": cam.last_seen,
            "last_seen_at": cam.last_seen,
            "ip_address": cam.ip_address,
        },
    }


@app.get("/api/admin/cameras")
def api_admin_cameras(db: Session = Depends(get_db), _: str = Depends(require_token)):
    return get_cameras(db, _)


@app.post("/api/admin/cameras")
def api_admin_create_camera(payload: schemas.CameraCreate, db: Session = Depends(get_db), _: str = Depends(require_token)):
    return post_camera(payload, db, _)


@app.put("/api/admin/cameras/{camera_id}")
def api_admin_update_camera(camera_id: str, payload: schemas.CameraUpdate, db: Session = Depends(get_db), _: str = Depends(require_token)):
    return put_camera(camera_id, payload, db, _)


@app.delete("/api/admin/cameras/{camera_id}")
def api_admin_delete_camera(camera_id: str, db: Session = Depends(get_db), _: str = Depends(require_token)):
    return delete_camera(camera_id, db, _)


@app.get("/api/device-status")
def api_device_status(db: Session = Depends(get_db), _: str = Depends(require_token)):
    return {"ok": True, "devices": crud.list_devices_map(db)}


@app.get("/api/violations/latest")
def api_violations_latest(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    rows = crud.list_violations(db, limit=limit)
    data = [crud.violation_to_public_dict(db, v) for v in rows]
    return {"ok": True, "violations": data, "data": data}


@app.get("/")
def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/main")
def main_page():
    return FileResponse(FRONTEND_DIR / "main.html")


@app.get("/login")
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/index")
def index_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/imge/{filename:path}")
def serve_image(filename: str):
    for root_dir in (IMAGE_DIR, LEGACY_IMAGE_DIR):
        candidate = (root_dir / filename).resolve()
        try:
            candidate.relative_to(root_dir.resolve())
        except Exception:
            continue
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="Image not found")


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


@app.get("/{file_path:path}")
def frontend_fallback(file_path: str):
    if file_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    target = (FRONTEND_DIR / file_path).resolve()
    if FRONTEND_DIR.exists():
        try:
            target.relative_to(FRONTEND_DIR.resolve())
            if target.exists() and target.is_file():
                return FileResponse(target)
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn

    host = (os.getenv("HOST") or "0.0.0.0").strip()
    port = int((os.getenv("PORT") or "5050").strip())

    uvicorn.run("app:app", host=host, port=port, reload=False)
