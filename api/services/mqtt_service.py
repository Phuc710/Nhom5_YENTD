"""
MQTTService — MQTT client for ESP32-S3 camera control, traffic lights, and 7-segment displays.

Uses paho-mqtt. Runs on a background thread.

Topic structure:
    trafficcam/camera/{camera_id}/control      → Backend → ESP32
    trafficcam/camera/{camera_id}/status        ← ESP32 → Backend
    trafficcam/camera/{camera_id}/telemetry     ← ESP32 → Backend
    trafficcam/traffic_light/{id}/control       → Backend → Traffic light PCB
    trafficcam/traffic_light/{id}/state         ← PCB → Backend
    trafficcam/display/{id}/control             → Backend → 7-segment display
"""
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from api.config import settings

logger = logging.getLogger("trafficcam.mqtt")

# Topic prefixes
TOPIC_PREFIX = "trafficcam"
CAMERA_CONTROL = f"{TOPIC_PREFIX}/camera/{{camera_id}}/control"
CAMERA_STATUS = f"{TOPIC_PREFIX}/camera/+/status"
CAMERA_TELEMETRY = f"{TOPIC_PREFIX}/camera/+/telemetry"
TRAFFIC_LIGHT_CONTROL = f"{TOPIC_PREFIX}/traffic_light/{{light_id}}/control"
TRAFFIC_LIGHT_STATE = f"{TOPIC_PREFIX}/traffic_light/+/state"
DISPLAY_CONTROL = f"{TOPIC_PREFIX}/display/{{display_id}}/control"


class MQTTService:
    """
    MQTT client service.
    Connect/disconnect managed by app lifespan.
    """

    def __init__(self) -> None:
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        self._callbacks: Dict[str, List[Callable]] = {}
        # Store received messages for status queries
        self._device_status: Dict[str, Dict] = {}
        self._telemetry: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        """Connect to MQTT broker. Called during app lifespan."""
        if not settings.mqtt_configured:
            logger.info("MQTT not enabled (TRAFFIC_MQTT_ENABLED=false). MQTT features disabled.")
            return

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
            return

        self._client = mqtt.Client(
            client_id=settings.mqtt_client_id,
            protocol=mqtt.MQTTv311,
        )

        # Auth
        if settings.mqtt_username:
            self._client.username_pw_set(
                settings.mqtt_username,
                settings.mqtt_password or None,
            )

        # Callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        try:
            self._client.connect(
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
                keepalive=60,
            )
            self._client.loop_start()
            logger.info(
                f"MQTT connecting to {settings.mqtt_broker_host}:{settings.mqtt_broker_port}..."
            )
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            self._client = None

    def shutdown(self) -> None:
        """Disconnect MQTT client."""
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False
            logger.info("MQTT disconnected.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_status(self) -> Dict:
        """Return MQTT connection status."""
        return {
            "connected": self._connected,
            "broker": f"{settings.mqtt_broker_host}:{settings.mqtt_broker_port}"
            if settings.mqtt_configured else "not configured",
            "enabled": settings.mqtt_enabled,
            "client_id": settings.mqtt_client_id,
        }

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        """
        Publish a message to an MQTT topic.

        Args:
            topic: MQTT topic string
            payload: Dict or string payload (dicts are JSON-encoded)
            qos: Quality of service (0, 1, 2)
            retain: Whether broker should retain message
        """
        if self._client is None or not self._connected:
            logger.warning(f"MQTT not connected. Cannot publish to {topic}")
            return False

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        try:
            result = self._client.publish(topic, payload, qos=qos, retain=retain)
            if result.rc == 0:
                logger.debug(f"MQTT published to {topic}: {payload[:100]}")
                return True
            else:
                logger.error(f"MQTT publish failed (rc={result.rc}): {topic}")
                return False
        except Exception as e:
            logger.error(f"MQTT publish error: {e}")
            return False

    def subscribe(self, topic: str, callback: Optional[Callable] = None) -> bool:
        """Subscribe to an MQTT topic."""
        if self._client is None:
            return False
        try:
            self._client.subscribe(topic, qos=1)
            if callback:
                if topic not in self._callbacks:
                    self._callbacks[topic] = []
                self._callbacks[topic].append(callback)
            logger.info(f"MQTT subscribed: {topic}")
            return True
        except Exception as e:
            logger.error(f"MQTT subscribe error: {e}")
            return False

    # ------------------------------------------------------------------
    # High-level control methods
    # ------------------------------------------------------------------

    def control_traffic_light(self, light_id: int, state: str, duration_s: Optional[int] = None) -> bool:
        """
        Send traffic light control command.

        Args:
            light_id: Traffic light identifier
            state: "red", "yellow", "green", "off", "flash_yellow"
            duration_s: Optional duration in seconds
        """
        topic = TRAFFIC_LIGHT_CONTROL.format(light_id=light_id)
        payload = {"state": state, "timestamp": time.time()}
        if duration_s is not None:
            payload["duration_s"] = duration_s
        return self.publish(topic, payload)

    def control_display(self, display_id: int, text: str, brightness: int = 7) -> bool:
        """
        Send 7-segment display control command.

        Args:
            display_id: Display identifier
            text: Text to show (numbers, limited chars)
            brightness: 0-15 brightness level
        """
        topic = DISPLAY_CONTROL.format(display_id=display_id)
        payload = {
            "text": text,
            "brightness": min(max(brightness, 0), 15),
            "timestamp": time.time(),
        }
        return self.publish(topic, payload)

    def control_camera(self, camera_id: int, command: str, params: Optional[Dict] = None) -> bool:
        """
        Send camera control command to ESP32-S3.

        Args:
            camera_id: Camera identifier
            command: "restart", "rotate", "set_resolution", "set_quality", "stream_start", "stream_stop"
            params: Additional parameters for the command
        """
        topic = CAMERA_CONTROL.format(camera_id=camera_id)
        payload = {"command": command, "timestamp": time.time()}
        if params:
            payload["params"] = params
        return self.publish(topic, payload)

    def get_device_telemetry(self, camera_id: Optional[int] = None) -> Dict:
        """Return latest cached telemetry data."""
        if camera_id is not None:
            return self._telemetry.get(str(camera_id), {})
        return dict(self._telemetry)

    def get_device_status_cache(self, camera_id: Optional[int] = None) -> Dict:
        """Return latest cached device status."""
        if camera_id is not None:
            return self._device_status.get(str(camera_id), {})
        return dict(self._device_status)

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected to broker.")
            # Subscribe to device status and telemetry topics
            client.subscribe(CAMERA_STATUS, qos=1)
            client.subscribe(CAMERA_TELEMETRY, qos=1)
            client.subscribe(TRAFFIC_LIGHT_STATE, qos=1)
        else:
            self._connected = False
            logger.error(f"MQTT connection failed with rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}). Will auto-reconnect.")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            topic = msg.topic
            payload_str = msg.payload.decode("utf-8", errors="replace")

            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                payload = {"raw": payload_str}

            # Parse camera_id from topic
            parts = topic.split("/")

            # Cache status messages: trafficcam/camera/{id}/status
            if len(parts) >= 4 and parts[1] == "camera" and parts[3] == "status":
                cam_id = parts[2]
                self._device_status[cam_id] = payload
                logger.debug(f"Camera {cam_id} status: {payload}")

            # Cache telemetry: trafficcam/camera/{id}/telemetry
            elif len(parts) >= 4 and parts[1] == "camera" and parts[3] == "telemetry":
                cam_id = parts[2]
                self._telemetry[cam_id] = payload
                logger.debug(f"Camera {cam_id} telemetry: {payload}")

            # Traffic light state: trafficcam/traffic_light/{id}/state
            elif len(parts) >= 4 and parts[1] == "traffic_light" and parts[3] == "state":
                light_id = parts[2]
                self._device_status[f"light_{light_id}"] = payload
                logger.debug(f"Traffic light {light_id} state: {payload}")

            # Fire registered callbacks
            for pattern, cbs in self._callbacks.items():
                # Simple wildcard match
                if self._topic_matches(pattern, topic):
                    for cb in cbs:
                        try:
                            cb(topic, payload)
                        except Exception as e:
                            logger.error(f"MQTT callback error: {e}")

        except Exception as e:
            logger.error(f"MQTT message handling error: {e}")

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Simple MQTT wildcard match (+ and #)."""
        pat_parts = pattern.split("/")
        top_parts = topic.split("/")
        for i, pp in enumerate(pat_parts):
            if pp == "#":
                return True
            if i >= len(top_parts):
                return False
            if pp != "+" and pp != top_parts[i]:
                return False
        return len(pat_parts) == len(top_parts)
