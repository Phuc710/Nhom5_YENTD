"""
MQTT Client — Subscribe Mosquitto broker, nhận telemetry từ ESP32.
Chạy trong QThread riêng, emit signals về MainWindow.

Device routing:
  ESP32-S3 Camera → pub KAI/cameras/{name}/telemetry  (stream telemetry)
  ESP32_PCB       → pub KAI/pcb/{name}/telemetry      (traffic light telemetry)
  Backend         → pub KAI/pcb/{name}/cmd             (điều khiển đèn)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import paho.mqtt.client as mqtt
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# ── Topics Subscribe ──────────────────────────────────────────────────────────
# Camera ESP32-S3: stream telemetry
TOPIC_CAM_TELEMETRY  = "KAI/cameras/+/telemetry"

# PCB ESP32: traffic light telemetry + online/offline status
TOPIC_PCB_TELEMETRY  = "KAI/pcb/+/telemetry"
TOPIC_PCB_STATUS     = "KAI/pcb/+/status"

# Legacy fallback
TOPIC_TRAFFIC_LEGACY = "ytd/traffic/#"
TOPIC_HEALTH_LEGACY  = "ytd/health/#"


class MqttClientThread(QThread):
    """Paho MQTT chạy trong QThread, emit signals khi nhận data."""

    # Signals
    light_changed   = pyqtSignal(str, str)   # (device_name, state: RED/GREEN/YELLOW)
    telemetry_recv  = pyqtSignal(str, dict)  # (device_name, payload)
    traffic_status  = pyqtSignal(dict)       # full tl status dict từ PCB
    pcb_status      = pyqtSignal(str, bool)  # (pcb_name, online)
    connected       = pyqtSignal()
    disconnected    = pyqtSignal()

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1888,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._client: Optional[mqtt.Client] = None
        self._running = False

    # ── QThread entry ──────────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        self._client = mqtt.Client(client_id="ytd-pyqt5-monitor", clean_session=True)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

        try:
            self._client.connect(self._host, self._port, keepalive=30)
            logger.info("MQTT connecting to %s:%d", self._host, self._port)
            self._client.loop_forever()
        except Exception as exc:
            logger.error("MQTT connection failed: %s", exc)
            self.disconnected.emit()

    def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                self._client.disconnect()
                self._client.loop_stop()
            except Exception:
                pass

    # ── Paho callbacks ─────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected (rc=%d)", rc)
            client.subscribe([
                (TOPIC_CAM_TELEMETRY,  0),  # Camera ESP32-S3 telemetry
                (TOPIC_PCB_TELEMETRY,  1),  # PCB traffic light telemetry
                (TOPIC_PCB_STATUS,     1),  # PCB online/offline
                (TOPIC_TRAFFIC_LEGACY, 0),  # Legacy
                (TOPIC_HEALTH_LEGACY,  0),  # Legacy
            ])
            self.connected.emit()
        else:
            logger.warning("MQTT connect rejected rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        logger.warning("MQTT disconnected rc=%d", rc)
        self.disconnected.emit()

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return

        topic: str = msg.topic
        parts = topic.split("/")

        # ── KAI/pcb/{name}/telemetry — Traffic Light PCB ──────────────────────
        if topic.startswith("KAI/pcb/") and topic.endswith("/telemetry"):
            device_name = parts[2] if len(parts) > 2 else "unknown"
            self.telemetry_recv.emit(device_name, payload)

            # ← Suy ra PCB đang online từ chính telemetry (ESP32 không publish /status)
            self.pcb_status.emit(device_name, True)

            # Trạng thái đèn → light_changed
            state = str(payload.get("light_state", "")).upper()
            if state in ("RED", "GREEN", "YELLOW"):
                self.light_changed.emit(device_name, state)

            # Full traffic status (có operation_mode, remain_sec, ...)
            if "operation_mode" in payload:
                self.traffic_status.emit(payload)
            return

        # ── KAI/pcb/{name}/status — PCB online/offline ────────────────────────
        if topic.startswith("KAI/pcb/") and topic.endswith("/status"):
            device_name = parts[2] if len(parts) > 2 else "unknown"
            online = str(payload.get("status", "")).lower() == "online"
            self.pcb_status.emit(device_name, online)
            logger.info("PCB [%s] → %s", device_name, "online" if online else "offline")
            return

        # ── KAI/cameras/{name}/telemetry — Camera ESP32-S3 ───────────────────
        if topic.startswith("KAI/cameras/") and topic.endswith("/telemetry"):
            device_name = parts[2] if len(parts) > 2 else "unknown"
            self.telemetry_recv.emit(device_name, payload)
            # Camera có thể vẫn gửi light_state (legacy), không bỏ
            state = str(payload.get("light_state", "")).upper()
            if state in ("RED", "GREEN", "YELLOW"):
                self.light_changed.emit(device_name, state)
            if "operation_mode" in payload:
                self.traffic_status.emit(payload)
            return

        # ── Legacy topics ─────────────────────────────────────────────────────
        if "traffic" in topic:
            mac = parts[2] if len(parts) > 2 else "unknown"
            state = str(payload.get("light_state", "")).upper()
            if state in ("RED", "GREEN", "YELLOW"):
                self.light_changed.emit(mac, state)
        elif "telemetry" in topic or "health" in topic:
            mac = parts[2] if len(parts) > 2 else "unknown"
            self.telemetry_recv.emit(mac, payload)

    # ── Commands → ESP32_PCB via Mosquitto ────────────────────────────────────
    # Backend publish tới KAI/pcb/{pcb_device_name}/cmd
    # ESP32_PCB subscribe và thực thi

    def send_traffic_rpc(self, pcb_device: str, method: str) -> None:
        """Gửi lệnh điều khiển đèn đến ESP32_PCB qua Mosquitto.
        pcb_device: tên thiết bị PCB (ví dụ 'PCB-001'), KHÔNG phải camera name.
        method: setNormalMode | setEmergencyRed | setEmergencyGreen | getStatus
        """
        if not self._client:
            logger.warning("MQTT not connected, cannot send RPC")
            return
        topic   = f"KAI/pcb/{pcb_device}/cmd"
        payload = json.dumps({"method": method, "params": {}})
        try:
            self._client.publish(topic, payload, qos=1)
            logger.info("PCB CMD sent [%s → %s]: %s", pcb_device, topic, method)
        except Exception as exc:
            logger.error("Failed to send PCB CMD: %s", exc)

    def send_traffic_timing(self, pcb_device: str, red_ms: int, yellow_ms: int, green_ms: int) -> None:
        """Cập nhật timing đèn giao thông — gửi tới ESP32_PCB."""
        if not self._client:
            return
        topic   = f"KAI/pcb/{pcb_device}/cmd"
        payload = json.dumps({
            "method": "setTimings",
            "params": {
                "tl_red_ms":    red_ms,
                "tl_yellow_ms": yellow_ms,
                "tl_green_ms":  green_ms,
            },
        })
        try:
            self._client.publish(topic, payload, qos=1)
            logger.info("PCB timing sent [%s]: R=%d Y=%d G=%d ms",
                        pcb_device, red_ms, yellow_ms, green_ms)
        except Exception as exc:
            logger.error("Failed to send PCB timing: %s", exc)
