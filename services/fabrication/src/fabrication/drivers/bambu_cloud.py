"""Bambu Labs Cloud MQTT client for printer telemetry and control.

Connects to Bambu Labs cloud broker to:
- Receive real-time printer telemetry
- Send control commands (pause, resume, stop)
- Discover bound printers
- Upload 3MF files and start prints directly (no G-code slicing needed)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import ssl
import time
import uuid
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

    async def upload_3mf(self, file_path: str | Path) -> dict:
        """
        Upload a 3MF file to Bambu cloud storage for printing.

        Args:
            file_path: Path to the 3MF file

        Returns:
            dict with 'success', 'file_url', 'file_name', 'md5' on success
            dict with 'error' on failure
        """
        if not self.is_logged_in:
            return {"error": "Not logged in to Bambu Labs"}

        file_path = Path(file_path)
        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        if not file_path.suffix.lower() == ".3mf":
            return {"error": "File must be a .3mf file"}

        # Read file and compute MD5
        file_data = file_path.read_bytes()
        file_md5 = hashlib.md5(file_data).hexdigest()
        file_name = file_path.name
        file_size = len(file_data)

        logger.info("Uploading 3MF file: %s (%d bytes, md5=%s)", file_name, file_size, file_md5)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Step 1: Request upload URL from Bambu API
                # The API returns a signed S3 URL for uploading
                upload_request = await client.post(
                    f"{BAMBU_API_BASE}/v1/iot-service/api/slicer/upload",
                    headers={"Authorization": f"Bearer {self._token.access_token}"},
                    json={
                        "name": file_name,
                        "size": file_size,
                        "md5": file_md5,
                    },
                )

                if upload_request.status_code != 200:
                    logger.error("Failed to get upload URL: %s", upload_request.text)
                    return {"error": f"Failed to get upload URL: {upload_request.status_code}"}

                upload_data = upload_request.json()
                upload_url = upload_data.get("url")
                osskey = upload_data.get("osskey") or upload_data.get("key")

                if not upload_url:
                    logger.error("No upload URL in response: %s", upload_data)
                    return {"error": "No upload URL returned"}

                logger.info("Got upload URL, uploading file...")

                # Step 2: Upload file to S3/OSS
                # Use minimal headers to avoid signature mismatch
                upload_response = await client.put(
                    upload_url,
                    content=file_data,
                    headers={"Content-Type": "application/octet-stream"},
                )

                if upload_response.status_code not in (200, 201, 204):
                    logger.error("File upload failed: %s", upload_response.text)
                    return {"error": f"File upload failed: {upload_response.status_code}"}

                logger.info("File uploaded successfully to cloud storage")

                # Construct the cloud file URL for printing
                # The printer will download from this URL
                cloud_file_url = upload_data.get("file_url") or f"cloud://{osskey}"

                return {
                    "success": True,
                    "file_url": cloud_file_url,
                    "file_name": file_name,
                    "md5": file_md5,
                    "osskey": osskey,
                }

        except Exception as e:
            logger.error("Error uploading 3MF: %s", e)
            return {"error": str(e)}

    async def start_print_3mf(
        self,
        device_id: str,
        file_url: str,
        file_name: str,
        md5: str,
        *,
        plate_number: int = 1,
        use_ams: bool = True,
        bed_leveling: bool = True,
        flow_calibration: bool = True,
        vibration_calibration: bool = True,
        timelapse: bool = False,
    ) -> dict:
        """
        Start a print job on a Bambu printer using a cloud-uploaded 3MF file.

        Args:
            device_id: Printer serial number
            file_url: Cloud URL of the uploaded 3MF file
            file_name: Name of the 3MF file
            md5: MD5 hash of the file
            plate_number: Plate number to print (default 1)
            use_ams: Whether to use AMS (default True)
            bed_leveling: Enable bed leveling (default True)
            flow_calibration: Enable flow calibration (default True)
            vibration_calibration: Enable vibration calibration (default True)
            timelapse: Enable timelapse recording (default False)

        Returns:
            dict with 'success' and 'task_id' on success
            dict with 'error' on failure
        """
        if not self._client or not self._connected:
            return {"error": "MQTT not connected"}

        if device_id not in self._printers:
            return {"error": f"Unknown printer: {device_id}"}

        # Generate unique task ID
        task_id = str(uuid.uuid4())
        sequence_id = str(int(time.time() * 1000))

        # Build the print command
        # The printer expects the gcode path inside the 3MF (usually Metadata/plate_X.gcode)
        gcode_path = f"Metadata/plate_{plate_number}.gcode"

        message = {
            "print": {
                "sequence_id": sequence_id,
                "command": "project_file",
                "param": gcode_path,
                "project_id": "0",
                "profile_id": "0",
                "task_id": task_id,
                "subtask_id": "0",
                "subtask_name": file_name,
                "url": file_url,
                "md5": md5,
                "timelapse": timelapse,
                "bed_leveling": bed_leveling,
                "flow_cali": flow_calibration,
                "vibration_cali": vibration_calibration,
                "layer_inspect": False,
                "use_ams": use_ams,
            }
        }

        topic = f"device/{device_id}/request"
        try:
            self._client.publish(topic, json.dumps(message))
            logger.info("Sent print command for %s to %s (task_id=%s)", file_name, device_id, task_id)
            return {"success": True, "task_id": task_id}
        except Exception as e:
            logger.error("Failed to send print command: %s", e)
            return {"error": str(e)}

    async def print_3mf_file(
        self,
        device_id: str,
        file_path: str | Path,
        **print_options: Any,
    ) -> dict:
        """
        Upload a 3MF file and start printing on a Bambu printer.

        This is a convenience method that combines upload_3mf() and start_print_3mf().

        Args:
            device_id: Printer serial number
            file_path: Path to the 3MF file
            **print_options: Options passed to start_print_3mf()

        Returns:
            dict with 'success', 'task_id', 'file_url' on success
            dict with 'error' on failure
        """
        # Upload the file
        upload_result = await self.upload_3mf(file_path)
        if not upload_result.get("success"):
            return upload_result

        # Start the print
        print_result = await self.start_print_3mf(
            device_id=device_id,
            file_url=upload_result["file_url"],
            file_name=upload_result["file_name"],
            md5=upload_result["md5"],
            **print_options,
        )

        if print_result.get("success"):
            return {
                **print_result,
                "file_url": upload_result["file_url"],
            }
        return print_result

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
