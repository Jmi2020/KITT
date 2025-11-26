"""Bambu Labs Cloud MQTT client for printer telemetry and control.

Connects to Bambu Labs cloud broker to:
- Receive real-time printer telemetry
- Send control commands (pause, resume, stop)
- Discover bound printers
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore

logger = logging.getLogger(__name__)

BAMBU_API_BASE = "https://api.bambulab.com"
BAMBU_MQTT_BROKER = os.getenv("BAMBU_CLOUD_URL", "mqtts://us.mqtt.bambulab.com:8883")


@dataclass
class BambuToken:
    """OAuth token for Bambu Labs API."""

    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp


@dataclass
class BambuPrinter:
    """Information about a Bambu Labs printer."""

    device_id: str
    name: str
    model: str = ""
    online: bool = False


@dataclass
class PrinterTelemetry:
    """Real-time telemetry from a printer."""

    device_id: str
    gcode_state: str = "UNKNOWN"
    percent: int = 0
    remaining_time: int = 0
    bed_temp: float = 0.0
    bed_target: float = 0.0
    nozzle_temp: float = 0.0
    nozzle_target: float = 0.0
    fan_speed: int = 0
    layer_num: int = 0
    total_layers: int = 0
    ams_status: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)


class BambuCloudClient:
    """Client for Bambu Labs cloud MQTT integration."""

    def __init__(
        self,
        token: BambuToken | None = None,
        data_dir: str | Path | None = None,
        on_telemetry: Callable[[str, PrinterTelemetry], None] | None = None,
    ) -> None:
        if mqtt is None:
            raise RuntimeError("paho-mqtt not installed. Run: pip install paho-mqtt")

        self._token = token
        self._data_dir = Path(data_dir) if data_dir else Path("data/bambu")
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._client: mqtt.Client | None = None
        self._printers: dict[str, BambuPrinter] = {}
        self._telemetry: dict[str, PrinterTelemetry] = {}
        self._connected = False
        self._on_telemetry = on_telemetry
        self._push_interval_task: asyncio.Task | None = None

        # Load saved token if not provided
        if not self._token:
            self._load_token()

    def _load_token(self) -> None:
        """Load token from disk."""
        token_path = self._data_dir / "token.json"
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text())
                self._token = BambuToken(
                    access_token=data["access_token"],
                    refresh_token=data["refresh_token"],
                    expires_at=data["expires_at"],
                )
                logger.info("Loaded Bambu token from disk")
            except Exception as e:
                logger.warning("Failed to load token: %s", e)

    def _save_token(self) -> None:
        """Save token to disk."""
        if not self._token:
            return
        token_path = self._data_dir / "token.json"
        token_path.write_text(json.dumps({
            "access_token": self._token.access_token,
            "refresh_token": self._token.refresh_token,
            "expires_at": self._token.expires_at,
        }))
        logger.info("Saved Bambu token to disk")

    @property
    def is_logged_in(self) -> bool:
        """Check if we have a valid token."""
        return (
            self._token is not None
            and self._token.access_token
            and self._token.expires_at > time.time()
        )

    @property
    def is_connected(self) -> bool:
        """Check if MQTT is connected."""
        return self._connected

    async def login(self, email: str, password: str) -> dict:
        """
        Login to Bambu Labs cloud API.

        Returns:
            {"success": True} on success
            {"error": str, "needs_verification": bool} on failure
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BAMBU_API_BASE}/v1/user-service/user/login",
                json={"account": email, "password": password, "apiError": ""},
            )

            if response.status_code != 200:
                return {"error": f"Login failed: {response.status_code}"}

            data = response.json()

            # Direct login success
            if data.get("success") and data.get("accessToken"):
                self._token = BambuToken(
                    access_token=data["accessToken"],
                    refresh_token=data.get("refreshToken", ""),
                    expires_at=time.time() + data.get("expiresIn", 3600),
                )
                self._save_token()
                return {"success": True}

            # Verification code required
            if data.get("loginType") == "verifyCode":
                # Trigger email
                code_response = await client.post(
                    f"{BAMBU_API_BASE}/v1/user-service/user/sendemail/code",
                    json={"email": email, "type": "codeLogin"},
                )
                if code_response.status_code == 200:
                    return {"error": "Verification code required", "needs_verification": True}
                return {"error": "Failed to send verification code"}

            return {"error": data.get("message", data.get("error", "Login failed"))}

    async def verify_code(self, email: str, code: str) -> dict:
        """Verify email code for passwordless login."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BAMBU_API_BASE}/v1/user-service/user/login",
                json={"account": email, "code": code},
            )

            if response.status_code != 200:
                return {"error": "Invalid verification code"}

            data = response.json()
            if not data.get("accessToken"):
                return {"error": "Invalid verification response"}

            self._token = BambuToken(
                access_token=data["accessToken"],
                refresh_token=data.get("refreshToken", ""),
                expires_at=time.time() + data.get("expiresIn", 3600),
            )
            self._save_token()
            return {"success": True}

    async def fetch_printers(self) -> list[BambuPrinter]:
        """Fetch bound printers from Bambu Labs API."""
        if not self.is_logged_in:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BAMBU_API_BASE}/v1/iot-service/api/user/bind",
                headers={"Authorization": f"Bearer {self._token.access_token}"},
            )

            if response.status_code != 200:
                logger.error("Failed to fetch printers: %s", response.status_code)
                return []

            data = response.json()
            devices = data.get("devices", [])

            self._printers = {}
            for device in devices:
                printer = BambuPrinter(
                    device_id=device.get("dev_id", ""),
                    name=device.get("name", "Unknown"),
                    model=device.get("dev_model_name", ""),
                    online=device.get("online", False),
                )
                self._printers[printer.device_id] = printer

            logger.info("Fetched %d printers", len(self._printers))
            return list(self._printers.values())

    async def connect_mqtt(self) -> bool:
        """Connect to Bambu Labs cloud MQTT broker."""
        if not self.is_logged_in:
            logger.error("Cannot connect MQTT: not logged in")
            return False

        if not self._printers:
            await self.fetch_printers()
            if not self._printers:
                logger.error("Cannot connect MQTT: no printers found")
                return False

        # Get username (user ID)
        username = await self._get_username()

        # Parse broker URL
        broker_url = BAMBU_MQTT_BROKER.replace("mqtts://", "").replace("ssl://", "")
        host, port_str = broker_url.split(":")
        port = int(port_str)

        # Create MQTT client
        self._client = mqtt.Client(client_id=username, protocol=mqtt.MQTTv311)
        self._client.username_pw_set(username, self._token.access_token)

        # TLS setup
        self._client.tls_set(cert_reqs=ssl.CERT_NONE)
        self._client.tls_insecure_set(True)

        # Callbacks
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect(host, port, keepalive=60)
            self._client.loop_start()
            logger.info("Connecting to Bambu MQTT at %s:%d", host, port)
            return True
        except Exception as e:
            logger.error("MQTT connection failed: %s", e)
            return False

    async def _get_username(self) -> str:
        """Get MQTT username (user ID) from API."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BAMBU_API_BASE}/v1/design-user-service/my/preference",
                    headers={"Authorization": f"Bearer {self._token.access_token}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("uid"):
                        return f"u_{data['uid']}"
        except Exception:
            pass
        return f"u_{int(time.time())}"

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: dict, rc: int) -> None:
        """MQTT connect callback."""
        if rc == 0:
            self._connected = True
            logger.info("Connected to Bambu MQTT broker")

            # Subscribe to all printer report topics
            for device_id in self._printers:
                topic = f"device/{device_id}/report"
                client.subscribe(topic)
                logger.info("Subscribed to %s", topic)

                # Request initial status
                self._send_pushall(device_id)
        else:
            logger.error("MQTT connection failed with code %d", rc)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        """MQTT message callback."""
        try:
            # Parse topic: device/{device_id}/report
            parts = msg.topic.split("/")
            if len(parts) < 2:
                return
            device_id = parts[1]

            # Parse payload
            payload = json.loads(msg.payload.decode())

            # Extract telemetry data
            print_data = payload.get("print", payload)

            # Update telemetry cache
            if device_id not in self._telemetry:
                self._telemetry[device_id] = PrinterTelemetry(device_id=device_id)

            telem = self._telemetry[device_id]
            telem.gcode_state = print_data.get("gcode_state", telem.gcode_state)
            telem.percent = print_data.get("mc_percent", telem.percent)
            telem.remaining_time = print_data.get("mc_remaining_time", telem.remaining_time)
            telem.bed_temp = print_data.get("bed_temper", telem.bed_temp)
            telem.bed_target = print_data.get("bed_target_temper", telem.bed_target)
            telem.nozzle_temp = print_data.get("nozzle_temper", telem.nozzle_temp)
            telem.nozzle_target = print_data.get("nozzle_target_temper", telem.nozzle_target)
            telem.fan_speed = print_data.get("cooling_fan_speed", telem.fan_speed)
            telem.layer_num = print_data.get("layer_num", telem.layer_num)
            telem.total_layers = print_data.get("total_layer_num", telem.total_layers)
            telem.raw_data = {**telem.raw_data, **print_data}
            telem.last_update = time.time()

            # AMS status
            if "ams" in print_data:
                telem.ams_status = print_data["ams"]

            # Callback
            if self._on_telemetry:
                self._on_telemetry(device_id, telem)

        except Exception as e:
            logger.error("Error processing MQTT message: %s", e)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        """MQTT disconnect callback."""
        self._connected = False
        logger.info("Disconnected from Bambu MQTT broker (rc=%d)", rc)

    def _send_pushall(self, device_id: str) -> None:
        """Request full status from printer."""
        if not self._client or not self._connected:
            return

        topic = f"device/{device_id}/request"
        message = {
            "pushing": {
                "sequence_id": str(int(time.time() * 1000)),
                "command": "pushall",
                "version": 1,
                "push_target": 1,
            }
        }
        self._client.publish(topic, json.dumps(message))

    async def send_command(self, device_id: str, command: str) -> bool:
        """
        Send control command to printer.

        Args:
            device_id: Printer serial number
            command: One of 'pause', 'resume', 'stop'

        Returns:
            True if sent successfully
        """
        if not self._client or not self._connected:
            logger.error("Cannot send command: MQTT not connected")
            return False

        if command not in ("pause", "resume", "stop"):
            logger.error("Invalid command: %s", command)
            return False

        topic = f"device/{device_id}/request"
        message = {
            "print": {
                "sequence_id": str(int(time.time() * 1000)),
                "command": command,
                "param": "",
            }
        }
        self._client.publish(topic, json.dumps(message))
        logger.info("Sent %s command to %s", command, device_id)
        return True

    def get_telemetry(self, device_id: str) -> PrinterTelemetry | None:
        """Get cached telemetry for a printer."""
        return self._telemetry.get(device_id)

    def get_all_telemetry(self) -> dict[str, PrinterTelemetry]:
        """Get all cached telemetry."""
        return dict(self._telemetry)

    def get_printers(self) -> list[BambuPrinter]:
        """Get list of known printers."""
        return list(self._printers.values())

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected = False
        logger.info("Disconnected from Bambu MQTT")


# Singleton instance
_client: BambuCloudClient | None = None


def get_bambu_client() -> BambuCloudClient:
    """Get or create the Bambu cloud client singleton."""
    global _client
    if _client is None:
        _client = BambuCloudClient()
    return _client
