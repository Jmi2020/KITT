"""Bamboo Labs MQTT driver for Bamboo H2D printer.

Bamboo Labs printers use MQTT for control and status updates. This driver
implements the Bamboo MQTT protocol for automated print execution.

Protocol Documentation: https://github.com/bambulab/BambuStudio/wiki/MQTT-API
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt

from common.logging import get_logger

from .base import (
    PrinterCapabilities,
    PrinterDriver,
    PrinterState,
    PrinterStatus,
)

LOGGER = get_logger(__name__)


class BambuMqttDriver(PrinterDriver):
    """Bamboo Labs MQTT driver for H2D printer.

    Supports:
    - Bamboo Labs H2D (Hybrid Direct Drive)
    - Other Bamboo Labs printers with MQTT API

    Configuration:
    {
        "mqtt_broker": "bamboo-h2d.local",  # Printer hostname/IP
        "mqtt_port": 1883,
        "device_id": "01S00XXXXXXXXX",  # Printer serial number
        "access_code": "12345678",  # 8-digit access code from printer screen
        "username": "bblp",  # Default username
    }

    MQTT Topics:
    - device/{device_id}/request - Send commands to printer
    - device/{device_id}/report - Receive status updates from printer
    """

    def __init__(self, printer_id: str, config: dict):
        """Initialize Bamboo MQTT driver.

        Args:
            printer_id: Unique printer identifier
            config: Driver configuration with MQTT broker, device_id, access_code
        """
        super().__init__(printer_id, config)

        self.mqtt_broker = config["mqtt_broker"]
        self.mqtt_port = config.get("mqtt_port", 1883)
        self.device_id = config["device_id"]
        self.access_code = config["access_code"]
        self.username = config.get("username", "bblp")

        # MQTT topics
        self.topic_request = f"device/{self.device_id}/request"
        self.topic_report = f"device/{self.device_id}/report"

        # MQTT client
        self.client = mqtt.Client(client_id=f"kitty-{printer_id}")
        self.client.username_pw_set(self.username, self.access_code)

        # Status tracking
        self._last_status: Optional[PrinterStatus] = None
        self._status_lock = asyncio.Lock()
        self._connected = False

        # Setup callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            LOGGER.info(
                "Connected to Bamboo printer via MQTT",
                printer_id=self.printer_id,
                device_id=self.device_id,
            )
            # Subscribe to status reports
            client.subscribe(self.topic_report)
            self._connected = True
        else:
            LOGGER.error(
                "Failed to connect to Bamboo printer",
                printer_id=self.printer_id,
                return_code=rc,
            )
            self._connected = False

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback."""
        LOGGER.warning(
            "Disconnected from Bamboo printer",
            printer_id=self.printer_id,
            return_code=rc,
        )
        self._connected = False

    def _on_message(self, client, userdata, msg):
        """MQTT message callback - processes status reports."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))

            # Extract print status from payload
            # Bamboo sends comprehensive status in "print" object
            print_data = payload.get("print", {})

            # Map Bamboo state to our PrinterState
            gcode_state = print_data.get("gcode_state", "UNKNOWN")
            state_map = {
                "IDLE": PrinterState.idle,
                "RUNNING": PrinterState.printing,
                "PAUSE": PrinterState.paused,
                "FINISH": PrinterState.complete,
                "FAILED": PrinterState.error,
            }
            state = state_map.get(gcode_state, PrinterState.offline)

            # Extract temperatures
            nozzle_temp = print_data.get("nozzle_temper")
            nozzle_target = print_data.get("nozzle_target_temper")
            bed_temp = print_data.get("bed_temper")
            bed_target = print_data.get("bed_target_temper")

            # Extract print progress
            mc_percent = print_data.get("mc_percent", 0)  # Print progress percentage
            current_layer = print_data.get("layer_num")
            total_layers = print_data.get("total_layer_num")
            mc_remaining_time = print_data.get("mc_remaining_time")  # Minutes
            print_duration = print_data.get("mc_print_time")  # Minutes

            # Extract file info
            current_file = print_data.get("gcode_file")

            # Build status object
            status = PrinterStatus(
                printer_id=self.printer_id,
                state=state,
                is_online=True,
                is_printing=(state == PrinterState.printing),
                nozzle_temp=nozzle_temp,
                nozzle_target=nozzle_target,
                bed_temp=bed_temp,
                bed_target=bed_target,
                current_file=current_file,
                progress_percent=mc_percent if current_file else None,
                print_duration_seconds=int(print_duration * 60) if print_duration else None,
                time_remaining_seconds=int(mc_remaining_time * 60) if mc_remaining_time else None,
                current_layer=current_layer,
                total_layers=total_layers,
            )

            # Update cached status
            asyncio.create_task(self._update_status(status))

        except Exception as e:
            LOGGER.error(
                "Failed to parse Bamboo status message",
                printer_id=self.printer_id,
                error=str(e),
                exc_info=True,
            )

    async def _update_status(self, status: PrinterStatus):
        """Update cached status (async-safe)."""
        async with self._status_lock:
            self._last_status = status

    async def connect(self) -> bool:
        """Establish connection to Bamboo printer via MQTT.

        Returns:
            True if connected successfully
        """
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self.client.loop_start()  # Start background MQTT thread

            # Wait for connection (with timeout)
            for _ in range(10):  # 5 second timeout
                await asyncio.sleep(0.5)
                if self._connected:
                    return True

            LOGGER.error(
                "Timeout connecting to Bamboo printer",
                printer_id=self.printer_id,
            )
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to connect to Bamboo printer",
                printer_id=self.printer_id,
                error=str(e),
                exc_info=True,
            )
            return False

    async def disconnect(self) -> None:
        """Close MQTT connection."""
        self.client.loop_stop()
        self.client.disconnect()
        self._connected = False
        LOGGER.info("Disconnected from Bamboo printer", printer_id=self.printer_id)

    async def is_connected(self) -> bool:
        """Check if driver is connected to printer."""
        return self._connected and self.client.is_connected()

    async def get_status(self) -> PrinterStatus:
        """Get current printer status.

        Returns cached status from MQTT messages.
        If no status cached yet, returns offline status.
        """
        async with self._status_lock:
            if self._last_status:
                return self._last_status

        # No status received yet
        return PrinterStatus(
            printer_id=self.printer_id,
            state=PrinterState.offline,
            is_online=False,
            is_printing=False,
            error_message="No status received from printer",
        )

    async def get_capabilities(self) -> PrinterCapabilities:
        """Get printer hardware capabilities.

        Bamboo H2D specifications.
        """
        return PrinterCapabilities(
            printer_id=self.printer_id,
            printer_type="bamboo_h2d",
            build_volume_x=256,  # 256x256x256mm
            build_volume_y=256,
            build_volume_z=256,
            has_camera=True,  # Built-in camera
            has_auto_leveling=True,  # Auto bed leveling
            supports_multi_color=True,  # Supports AMS (multi-material)
            supports_resume=True,  # Power loss recovery
            supported_materials=["PLA", "PETG", "ABS", "TPU", "PA", "PC"],
        )

    async def upload_gcode(self, gcode_path: str, filename: Optional[str] = None) -> str:
        """Upload G-code file to printer.

        Note: Bamboo printers typically use Bambu Studio to slice and send files.
        For automated workflows, G-code can be sent via:
        1. FTP server on printer (if enabled)
        2. Cloud (Bambu Handy app integration)
        3. MQTT file transfer (not well documented)

        This implementation uses MQTT project_file command with local path.

        Args:
            gcode_path: Local path to G-code file
            filename: Optional filename (defaults to basename)

        Returns:
            Filename on printer
        """
        gcode_file = Path(gcode_path)
        if not gcode_file.exists():
            raise FileNotFoundError(f"G-code file not found: {gcode_path}")

        if filename is None:
            filename = gcode_file.name

        # For Bamboo, we typically need to use the local path
        # This assumes the G-code is accessible to the printer
        # (e.g., on a network share or FTP)

        LOGGER.warning(
            "Bamboo G-code upload requires FTP or cloud integration",
            printer_id=self.printer_id,
            filename=filename,
            note="Using local path for now - ensure printer can access file",
        )

        return str(gcode_file.absolute())

    async def start_print(self, filename: str) -> bool:
        """Start printing a file.

        Args:
            filename: Full path to G-code file (must be accessible to printer)

        Returns:
            True if print started successfully
        """
        try:
            # Send print command via MQTT
            # https://github.com/bambulab/BambuStudio/wiki/MQTT-API#start-printing
            payload = {
                "print": {
                    "command": "project_file",
                    "param": filename,
                    "sequence_id": "0",  # Sequence tracking
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info(
                    "Sent start print command to Bamboo",
                    printer_id=self.printer_id,
                    filename=filename,
                )
                return True
            else:
                LOGGER.error(
                    "Failed to publish start print command",
                    printer_id=self.printer_id,
                    return_code=result.rc,
                )
                return False

        except Exception as e:
            LOGGER.error(
                "Failed to start print",
                printer_id=self.printer_id,
                error=str(e),
                exc_info=True,
            )
            return False

    async def pause_print(self) -> bool:
        """Pause current print."""
        try:
            payload = {
                "print": {
                    "command": "pause",
                    "sequence_id": "0",
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info("Paused print", printer_id=self.printer_id)
                return True
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to pause print",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False

    async def resume_print(self) -> bool:
        """Resume paused print."""
        try:
            payload = {
                "print": {
                    "command": "resume",
                    "sequence_id": "0",
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info("Resumed print", printer_id=self.printer_id)
                return True
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to resume print",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False

    async def cancel_print(self) -> bool:
        """Cancel current print."""
        try:
            payload = {
                "print": {
                    "command": "stop",
                    "sequence_id": "0",
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info("Cancelled print", printer_id=self.printer_id)
                return True
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to cancel print",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False

    async def set_bed_temperature(self, temp_celsius: float) -> bool:
        """Set bed target temperature.

        Note: Bamboo typically manages temperatures automatically.
        Manual control requires custom G-code commands.
        """
        try:
            payload = {
                "print": {
                    "command": "gcode_line",
                    "param": f"M140 S{temp_celsius}",
                    "sequence_id": "0",
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info(
                    "Set bed temperature",
                    printer_id=self.printer_id,
                    temp_celsius=temp_celsius,
                )
                return True
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to set bed temperature",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False

    async def set_nozzle_temperature(self, temp_celsius: float) -> bool:
        """Set nozzle target temperature."""
        try:
            payload = {
                "print": {
                    "command": "gcode_line",
                    "param": f"M104 S{temp_celsius}",
                    "sequence_id": "0",
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info(
                    "Set nozzle temperature",
                    printer_id=self.printer_id,
                    temp_celsius=temp_celsius,
                )
                return True
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to set nozzle temperature",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False

    async def home_axes(self, x: bool = True, y: bool = True, z: bool = True) -> bool:
        """Home printer axes."""
        try:
            # Build G28 command
            axes = ""
            if x:
                axes += " X"
            if y:
                axes += " Y"
            if z:
                axes += " Z"

            payload = {
                "print": {
                    "command": "gcode_line",
                    "param": f"G28{axes}",
                    "sequence_id": "0",
                }
            }

            message = json.dumps(payload)
            result = self.client.publish(self.topic_request, message, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                LOGGER.info(
                    "Homing axes",
                    printer_id=self.printer_id,
                    axes=axes.strip(),
                )
                return True
            return False

        except Exception as e:
            LOGGER.error(
                "Failed to home axes",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False
