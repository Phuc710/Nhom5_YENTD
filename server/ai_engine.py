from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import requests

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover
    mqtt = None

from image_processor import ImageProcessor, normalize_plate_text
from traffic_controller import TrafficController


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ai-engine")

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        val = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_env_file(BASE_DIR / "config.env")


def _env_str(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int((os.getenv(key) or str(default)).strip())
    except Exception:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float((os.getenv(key) or str(default)).strip())
    except Exception:
        return default


BACKEND_BASE_URL = _env_str("AI_BACKEND_URL", f"http://127.0.0.1:{_env_str('PORT', '5050')}")
BACKEND_TOKEN = _env_str("DASHBOARD_SECRET", _env_str("AI_BACKEND_TOKEN", "TRAFFIC_AI_TOKEN"))
CAMERA_CODE = _env_str("AI_CAMERA_CODE", _env_str("CAM_STATION_ID", "CAM-HCM-001"))
CAMERA_SOURCE = _env_int("LAPTOP_CAMERA_INDEX", 0)
MIN_OCR_CONFIDENCE = _env_float("AI_MIN_OCR_CONFIDENCE", 0.65)
POST_TIMEOUT_SECONDS = _env_float("AI_POST_TIMEOUT_SECONDS", 5.0)
VIOLATION_COOLDOWN_SECONDS = _env_float("AI_VIOLATION_COOLDOWN_SECONDS", 8.0)
FRAME_INTERVAL_SECONDS = _env_float("AI_FRAME_INTERVAL_SECONDS", 0.08)
DEFAULT_LIGHT_STATE = _env_str("AI_LIGHT_STATE", "RED").upper()

MQTT_ENABLED = _env_str("MQTT_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
MQTT_HOST = _env_str("MQTT_HOST", "127.0.0.1")
MQTT_PORT = _env_int("MQTT_PORT", 1883)
MQTT_USERNAME = _env_str("MQTT_USERNAME", "")
MQTT_PASSWORD = _env_str("MQTT_PASSWORD", "")
MQTT_TOPIC_PREFIX = _env_str("MQTT_TOPIC_PREFIX", "traffic").strip("/")

STORAGE_ROOT = REPO_DIR / "imge" / "violations"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


class LightStateProvider:
    def __init__(self, db_path: Path) -> None:
        self.controller: Optional[TrafficController] = None
        self.cached_state = DEFAULT_LIGHT_STATE if DEFAULT_LIGHT_STATE in {"RED", "GREEN", "YELLOW", "ALL_RED"} else "RED"
        self.last_refresh = 0.0
        try:
            self.controller = TrafficController(str(db_path))
            log.info("traffic runtime provider active via TrafficController")
        except Exception as exc:
            self.controller = None
            log.warning("traffic runtime unavailable, fallback light state=%s err=%s", self.cached_state, exc)

    def get_light_state(self) -> str:
        now = time.time()
        if now - self.last_refresh < 0.5:
            return self.cached_state
        self.last_refresh = now
        if self.controller is None:
            return self.cached_state
        try:
            state = str(self.controller.get_runtime().get("current_state") or self.cached_state).upper()
            if state in {"RED", "GREEN", "YELLOW", "ALL_RED"}:
                self.cached_state = state
        except Exception:
            pass
        return self.cached_state


class ViolationPublisher:
    def __init__(self, base_url: str, token: str) -> None:
        self.url = f"{base_url.rstrip('/')}/api/violations"
        self.token = token
        self.session = requests.Session()

    def send(self, payload: dict) -> Optional[dict]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        resp = self.session.post(self.url, headers=headers, data=json.dumps(payload), timeout=POST_TIMEOUT_SECONDS)
        if resp.status_code >= 300:
            body = resp.text[:250].replace("\n", " ")
            raise RuntimeError(f"backend returned {resp.status_code}: {body}")
        try:
            return resp.json()
        except Exception:
            return None


class ViolationMqttRelay:
    def __init__(self) -> None:
        self.client = None
        if not MQTT_ENABLED or mqtt is None:
            return
        try:
            self.client = mqtt.Client(client_id=f"ai-engine-{int(time.time())}")
            if MQTT_USERNAME:
                self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            self.client.loop_start()
            log.info("mqtt relay connected %s:%s", MQTT_HOST, MQTT_PORT)
        except Exception as exc:
            self.client = None
            log.warning("mqtt relay disabled err=%s", exc)

    def publish_violation(self, camera_code: str, payload: dict) -> None:
        if self.client is None:
            return
        topic = f"{MQTT_TOPIC_PREFIX}/camera/{camera_code}/violation"
        try:
            self.client.publish(topic, json.dumps(payload, ensure_ascii=True), qos=0)
        except Exception:
            pass


class AiRuntime:
    def __init__(self, app) -> None:
        self.app = app
        self.processor = ImageProcessor()
        self.publisher = ViolationPublisher(BACKEND_BASE_URL, BACKEND_TOKEN)
        self.relay = ViolationMqttRelay()
        self.light_provider = LightStateProvider(BASE_DIR / "traffic_ai.db")
        self.stop_event = threading.Event()
        self.last_sent: dict[tuple[str, str], float] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _camera_storage_dir(self) -> Path:
        now = datetime.now(timezone.utc)
        target = STORAGE_ROOT / CAMERA_CODE / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _save_image(self, image, path: Path) -> Optional[str]:
        if image is None:
            return None
        ok = cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return None
        relative = path.relative_to(REPO_DIR).as_posix()
        return f"/{relative}"

    def _is_duplicate(self, camera_code: str, plate_norm: str) -> bool:
        if not plate_norm:
            return False
        key = (camera_code, plate_norm)
        now = time.time()
        prev = self.last_sent.get(key, 0.0)
        self.last_sent[key] = now
        return (now - prev) < VIOLATION_COOLDOWN_SECONDS

    def _build_payload(self, frame, detection: dict, light_state: str) -> Optional[dict]:
        plate_number = (detection.get("plate_number") or "").strip()
        plate_norm = (detection.get("normalized_plate_number") or normalize_plate_text(plate_number)).strip()
        ocr_confidence = float(detection.get("ocr_confidence") or 0.0)

        if not plate_norm:
            return None
        if ocr_confidence < MIN_OCR_CONFIDENCE:
            return None
        if self._is_duplicate(CAMERA_CODE, plate_norm):
            return None

        storage_dir = self._camera_storage_dir()
        ts = datetime.now(timezone.utc)
        stamp = ts.strftime("%Y%m%dT%H%M%S") + f"_{int(ts.microsecond / 1000):03d}"
        safe_plate = "".join(ch for ch in plate_norm if ch.isalnum()) or "UNKNOWN"

        full_file = storage_dir / f"{safe_plate}_{stamp}_full.jpg"
        vehicle_file = storage_dir / f"{safe_plate}_{stamp}_vehicle.jpg"
        plate_file = storage_dir / f"{safe_plate}_{stamp}_plate.jpg"

        full_image_url = self._save_image(frame, full_file)
        vehicle_crop_url = self._save_image(detection.get("vehicle_crop") or frame, vehicle_file)
        plate_crop_url = self._save_image(detection.get("plate_crop"), plate_file)

        payload = {
            "camera_code": CAMERA_CODE,
            "plate_number": plate_number or plate_norm,
            "normalized_plate_number": plate_norm,
            "violation_type": "red_light_crossing",
            "violation_time": self._now_iso(),
            "full_image_url": full_image_url,
            "vehicle_crop_url": vehicle_crop_url,
            "plate_crop_url": plate_crop_url,
            "light_state": light_state,
            "ocr_text_raw": detection.get("ocr_text_raw") or plate_number or plate_norm,
            "ocr_confidence": round(ocr_confidence, 4),
            "vehicle_type": detection.get("vehicle_type") or "UNKNOWN",
            "status": "new",
        }
        return payload

    def run_loop(self) -> None:
        cap = cv2.VideoCapture(CAMERA_SOURCE)
        if not cap.isOpened():
            log.error("cannot open camera source=%s", CAMERA_SOURCE)
            return

        log.info("ai runtime started camera_code=%s source=%s backend=%s", CAMERA_CODE, CAMERA_SOURCE, BACKEND_BASE_URL)

        while not self.stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.1)
                continue

            self.app.latest_frame = frame.copy()
            light_state = self.light_provider.get_light_state()

            if light_state not in {"RED", "ALL_RED"}:
                time.sleep(FRAME_INTERVAL_SECONDS)
                continue

            detection = self.processor.build_violation_detection(frame)
            payload = self._build_payload(frame, detection, light_state)
            if payload is None:
                time.sleep(FRAME_INTERVAL_SECONDS)
                continue

            try:
                resp = self.publisher.send(payload) or {}
                violation_data = (resp.get("violation") if isinstance(resp, dict) else None) or payload
                self.relay.publish_violation(CAMERA_CODE, violation_data)
                log.info(
                    "violation created camera=%s plate=%s conf=%.2f light=%s",
                    CAMERA_CODE,
                    payload["normalized_plate_number"],
                    payload["ocr_confidence"],
                    light_state,
                )
            except Exception as exc:
                log.warning("failed to post violation: %s", exc)

            time.sleep(FRAME_INTERVAL_SECONDS)

        cap.release()


def ai_loop(app):
    runtime = AiRuntime(app)
    runtime.run_loop()


def start_ai(app):
    app.latest_frame = None
    thread = threading.Thread(target=ai_loop, args=(app,), daemon=True)
    thread.start()
    log.info("AI engine thread started")


def main() -> int:
    class _AppState:
        latest_frame = None

    dummy = _AppState()
    ai_loop(dummy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
