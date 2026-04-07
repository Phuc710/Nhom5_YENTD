"""
MQTT Client — Subscribe Mosquitto broker, nhận telemetry từ ESP32.
Chạy trong QThread riêng, emit signals về MainWindow.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import paho.mqtt.client as mqtt
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# Topics Mosquitto — khớp với ESP32 mqtt_app.c
TOPIC_TELEMETRY = "KAI/cameras/+/telemetry"   # ESP32 publish tại: KAI/cameras/{device_name}/telemetry
TOPIC_TRAFFIC   = "ytd/traffic/#"              # fallback topic cũ
TOPIC_HEALTH    = "ytd/health/#"


class MqttClientThread(QThread):
    """Paho MQTT chạy trong QThread, emit signals khi nhận data."""

    # Signals
    light_changed   = pyqtSignal(str, str)   # (device_name_or_mac, state: RED/GREEN/YELLOW)
    telemetry_recv  = pyqtSignal(str, dict)  # (device_name, payload)
    traffic_status  = pyqtSignal(dict)       # full tl status dict
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
                (TOPIC_TELEMETRY, 0),
                (TOPIC_TRAFFIC,   0),
                (TOPIC_HEALTH,    0),
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

        # KAI/cameras/{device_name}/telemetry
        if topic.startswith("KAI/cameras/") and topic.endswith("/telemetry"):
            device_name = parts[2] if len(parts) > 2 else "unknown"
            self.telemetry_recv.emit(device_name, payload)
            # Phân tích traffic light state
            state = str(payload.get("light_state", "")).upper()
            if state in ("RED", "GREEN", "YELLOW"):
                self.light_changed.emit(device_name, state)
            # Emit full traffic status nếu có operation_mode
            if "operation_mode" in payload:
                self.traffic_status.emit(payload)
            return

        # Legacy topics
        if "traffic" in topic:
            mac = parts[2] if len(parts) > 2 else "unknown"
            state = str(payload.get("light_state", "")).upper()
            if state in ("RED", "GREEN", "YELLOW"):
                self.light_changed.emit(mac, state)
        elif "telemetry" in topic or "health" in topic:
            mac = parts[2] if len(parts) > 2 else "unknown"
            self.telemetry_recv.emit(mac, payload)

    # ── Commands (ThingsBoard RPC via Mosquitto) ──────────────────────────────
    # ESP32 lắng nghe ThingsBoard RPC, nhưng ta publish qua Mosquitto
    # tới topic ytd/cmd/{device_name} dưới dạng ThingsBoard RPC format

    def send_traffic_rpc(self, device_name: str, method: str) -> None:
        """Gửi lệnh điều khiển đèn đến ESP32 qua Mosquitto.
        method: setNormalMode | setEmergencyRed | setEmergencyGreen
        """
        if not self._client:
            logger.warning("MQTT not connected, cannot send RPC")
            return
        topic = f"KAI/cameras/{device_name}/cmd"
        payload = json.dumps({"method": method, "params": {}})
        try:
            self._client.publish(topic, payload, qos=1)
            logger.info("Traffic CMD sent [%s]: %s", device_name, method)
        except Exception as exc:
            logger.error("Failed to send traffic CMD: %s", exc)

    def send_traffic_timing(self, device_name: str, red_ms: int, yellow_ms: int, green_ms: int) -> None:
        """Cập nhật timing đèn giao thông qua Mosquitto."""
        if not self._client:
            return
        topic = f"KAI/cameras/{device_name}/cmd"
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
            logger.info("Traffic timing sent: R=%d Y=%d G=%d ms", red_ms, yellow_ms, green_ms)
        except Exception as exc:
            logger.error("Failed to send timing: %s", exc)
