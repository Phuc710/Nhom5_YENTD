"""
Virtual ESP32 Camera Cluster Simulator (integration-first)

TEST-ONLY:
- This script is for integration testing only.
- Do NOT run in production service startup.

Quick start:
1) Start backend: `python server/app.py`
2) Run simulator (HTTP heartbeat):
   `python server/virtual_esp32_cluster.py --integration-test --transport http --count 12`
3) Optional MQTT mode:
   `python server/virtual_esp32_cluster.py --integration-test --transport mqtt --count 12 --mqtt-host localhost --mqtt-port 1883`
   Default topic template: `traffic/camera/{camera_code}/heartbeat`

Notes:
- Heartbeat interval is randomized between 3-5 seconds (configurable).
- Cameras can be marked as flaky to simulate temporary disconnect (no heartbeat sent).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import string
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None


log = logging.getLogger("esp32-simulator")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def random_camera_code(index: int, prefix: str) -> str:
    return f"{prefix}-{index:03d}"


def random_ip(index: int) -> str:
    block = 100 + (index % 100)
    return f"192.168.10.{block}"


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class CameraState:
    camera_code: str
    ip_address: str
    flaky: bool = False
    disconnected_until: float = 0.0
    temperature: float = 42.0
    signal_strength: int = 80
    latency_ms: int = 45

    def tick_metrics(self) -> None:
        self.temperature = clip(self.temperature + random.uniform(-0.7, 0.7), 36.0, 75.0)
        self.signal_strength = int(clip(self.signal_strength + random.randint(-4, 4), 20, 100))
        self.latency_ms = int(clip(self.latency_ms + random.randint(-8, 8), 10, 450))

    def maybe_disconnect(self, now_ts: float, disconnect_chance: float, min_sec: int, max_sec: int) -> None:
        if not self.flaky:
            return
        if now_ts < self.disconnected_until:
            return
        if random.random() < disconnect_chance:
            duration = random.randint(min_sec, max_sec)
            self.disconnected_until = now_ts + duration
            log.warning("camera=%s simulated disconnect for %ss", self.camera_code, duration)

    def is_disconnected(self, now_ts: float) -> bool:
        return now_ts < self.disconnected_until

    def heartbeat_payload(self) -> dict:
        return {
            "camera_code": self.camera_code,
            "status": "online",
            "latency_ms": self.latency_ms,
            "temperature": round(self.temperature, 2),
            "signal_strength": self.signal_strength,
            "ip_address": self.ip_address,
            "last_seen": utc_iso_now(),
        }


class HeartbeatSender:
    def send(self, payload: dict) -> None:
        raise NotImplementedError


class HttpHeartbeatSender(HeartbeatSender):
    def __init__(self, base_url: str, token: str, timeout_sec: float) -> None:
        self.url = f"{base_url.rstrip('/')}/api/devices/heartbeat"
        self.token = token.strip()
        self.timeout_sec = timeout_sec
        self.session = requests.Session()

    def send(self, payload: dict) -> None:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        resp = self.session.post(self.url, data=json.dumps(payload), headers=headers, timeout=self.timeout_sec)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")


class MqttHeartbeatSender(HeartbeatSender):
    def __init__(self, host: str, port: int, topic_template: str, username: str, password: str, keepalive: int) -> None:
        if mqtt is None:
            raise RuntimeError("paho-mqtt is not installed")
        client_id = f"esp32-sim-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
        self.client = mqtt.Client(client_id=client_id)
        if username:
            self.client.username_pw_set(username=username, password=password)
        self.host = host
        self.port = port
        self.topic_template = topic_template
        self.keepalive = keepalive
        self.client.connect(self.host, self.port, self.keepalive)
        self.client.loop_start()

    def send(self, payload: dict) -> None:
        topic = self.topic_template.format(camera_code=payload.get("camera_code", "unknown"))
        result = self.client.publish(topic, json.dumps(payload), qos=0)
        rc = getattr(result, "rc", 0)
        if rc != 0:
            raise RuntimeError(f"MQTT publish failed with rc={rc}")

    def close(self) -> None:
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass


class CameraSimulator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop_event = threading.Event()
        self.states = self._build_cameras(args.count, args.prefix, args.flaky_count)
        self.sender = self._build_sender(args)
        self.sent_ok = 0
        self.sent_fail = 0

    def _build_cameras(self, count: int, prefix: str, flaky_count: int) -> list[CameraState]:
        cameras = [
            CameraState(
                camera_code=random_camera_code(i + 1, prefix),
                ip_address=random_ip(i + 1),
            )
            for i in range(count)
        ]
        if cameras and flaky_count > 0:
            for idx in random.sample(range(len(cameras)), k=min(flaky_count, len(cameras))):
                cameras[idx].flaky = True
        return cameras

    def _build_sender(self, args: argparse.Namespace) -> HeartbeatSender:
        transport = args.transport.lower()
        if transport == "auto":
            transport = "http"

        if transport == "mqtt":
            return MqttHeartbeatSender(
                host=args.mqtt_host,
                port=args.mqtt_port,
                topic_template=args.mqtt_topic_template,
                username=args.mqtt_username,
                password=args.mqtt_password,
                keepalive=args.mqtt_keepalive,
            )
        return HttpHeartbeatSender(
            base_url=args.backend_url,
            token=args.token,
            timeout_sec=args.http_timeout,
        )

    def run(self) -> None:
        log.info(
            "start simulator transport=%s cameras=%s flaky=%s interval=[%ss,%ss]",
            self.args.transport,
            len(self.states),
            sum(1 for s in self.states if s.flaky),
            self.args.interval_min,
            self.args.interval_max,
        )
        for s in self.states:
            t = threading.Thread(target=self._camera_loop, args=(s,), daemon=True)
            t.start()

        while not self.stop_event.is_set():
            time.sleep(5.0)
            log.info("heartbeat summary ok=%s fail=%s", self.sent_ok, self.sent_fail)

    def shutdown(self) -> None:
        self.stop_event.set()
        if isinstance(self.sender, MqttHeartbeatSender):
            self.sender.close()

    def _camera_loop(self, state: CameraState) -> None:
        while not self.stop_event.is_set():
            now_ts = time.time()
            state.maybe_disconnect(
                now_ts=now_ts,
                disconnect_chance=self.args.disconnect_chance,
                min_sec=self.args.disconnect_min,
                max_sec=self.args.disconnect_max,
            )

            if not state.is_disconnected(now_ts):
                state.tick_metrics()
                payload = state.heartbeat_payload()
                try:
                    self.sender.send(payload)
                    self.sent_ok += 1
                    log.info(
                        "sent heartbeat camera=%s latency=%sms temp=%.1f signal=%s ip=%s",
                        state.camera_code,
                        payload["latency_ms"],
                        payload["temperature"],
                        payload["signal_strength"],
                        payload["ip_address"],
                    )
                except Exception as exc:
                    self.sent_fail += 1
                    log.error("send failed camera=%s err=%s", state.camera_code, exc)
            else:
                remaining = int(max(0, state.disconnected_until - now_ts))
                log.warning("camera=%s offline simulation remaining=%ss", state.camera_code, remaining)

            sleep_sec = random.uniform(self.args.interval_min, self.args.interval_max)
            self.stop_event.wait(timeout=sleep_sec)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESP32 multi-camera heartbeat simulator")
    parser.add_argument("--integration-test", action="store_true", help="required safety flag (test-only simulator)")
    parser.add_argument("--transport", default="auto", choices=["auto", "http", "mqtt"])
    parser.add_argument("--count", type=int, default=8, help="number of virtual cameras")
    parser.add_argument("--prefix", default="CAM-HCM-SIM", help="camera_code prefix")

    parser.add_argument("--interval-min", type=float, default=3.0, help="minimum heartbeat interval (sec)")
    parser.add_argument("--interval-max", type=float, default=5.0, help="maximum heartbeat interval (sec)")

    parser.add_argument("--flaky-count", type=int, default=2, help="how many cameras can disconnect randomly")
    parser.add_argument("--disconnect-chance", type=float, default=0.10, help="chance each cycle to start disconnect")
    parser.add_argument("--disconnect-min", type=int, default=12, help="minimum disconnect duration (sec)")
    parser.add_argument("--disconnect-max", type=int, default=30, help="maximum disconnect duration (sec)")

    parser.add_argument("--backend-url", default="http://127.0.0.1:5050")
    parser.add_argument("--token", default="TRAFFIC_AI_TOKEN")
    parser.add_argument("--http-timeout", type=float, default=4.0)

    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-topic-template", default="traffic/camera/{camera_code}/heartbeat")
    parser.add_argument("--mqtt-username", default="")
    parser.add_argument("--mqtt-password", default="")
    parser.add_argument("--mqtt-keepalive", type=int, default=60)

    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be >= 1")
    if args.interval_min <= 0 or args.interval_max <= 0 or args.interval_min > args.interval_max:
        parser.error("invalid heartbeat interval")
    if args.flaky_count < 0:
        parser.error("--flaky-count must be >= 0")
    if not (0.0 <= args.disconnect_chance <= 1.0):
        parser.error("--disconnect-chance must be in [0,1]")
    if args.disconnect_min < 1 or args.disconnect_max < args.disconnect_min:
        parser.error("invalid disconnect duration")
    if not args.integration_test:
        parser.error("Simulator is test-only. Re-run with --integration-test")
    return args


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    args = parse_args()
    sim = CameraSimulator(args)

    def _handle_stop(signum: int, frame: Optional[object]) -> None:
        log.info("received signal=%s, shutting down simulator", signum)
        sim.shutdown()

    signal.signal(signal.SIGINT, _handle_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_stop)

    try:
        sim.run()
    finally:
        sim.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
