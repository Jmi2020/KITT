"""Check printer availability via MQTT and HTTP."""

from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

import httpx
import paho.mqtt.client as mqtt

from common.config import Settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class PrinterStatus:
    """Printer availability and state."""
    printer_id: str
    is_online: bool
    is_printing: bool
    status: str  # "idle", "printing", "paused", "offline"
    current_job: Optional[str] = None
    progress_percent: Optional[float] = None
    bed_temp: Optional[float] = None
    bed_target: Optional[float] = None
    extruder_temp: Optional[float] = None
    extruder_target: Optional[float] = None
    last_updated: Optional[datetime] = None


class PrinterStatusChecker:
    """Query printer status with caching."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: Dict[str, PrinterStatus] = {}
        self._cache_ttl = timedelta(seconds=30)

        # Bamboo MQTT client
        self._bamboo_mqtt: Optional[mqtt.Client] = None
        self._bamboo_status: Dict = {}

    async def get_bamboo_status(self) -> PrinterStatus:
        """
        Check Bamboo H2D status via MQTT.

        Returns cached status if fresh (<30s old).
        """
        printer_id = "bamboo_h2d"

        # Check cache first
        if printer_id in self._cache:
            cached = self._cache[printer_id]
            age = datetime.now() - (cached.last_updated or datetime.min)
            if age < self._cache_ttl:
                LOGGER.debug("Using cached Bamboo status", age_seconds=age.total_seconds())
                return cached

        # Initialize MQTT client if needed
        if not self._bamboo_mqtt:
            self._init_bamboo_mqtt()

        # Wait up to 2 seconds for MQTT message
        await asyncio.sleep(2)

        # Parse status from last MQTT message
        print_state = self._bamboo_status.get("print", {}).get("gcode_state", "IDLE")
        is_printing = print_state in ["RUNNING", "PAUSE"]

        status = PrinterStatus(
            printer_id=printer_id,
            is_online=bool(self._bamboo_status),
            is_printing=is_printing,
            status="printing" if print_state == "RUNNING" else "idle" if print_state == "IDLE" else "offline",
            current_job=self._bamboo_status.get("print", {}).get("subtask_name"),
            progress_percent=self._bamboo_status.get("print", {}).get("mc_percent"),
            bed_temp=self._bamboo_status.get("temps", {}).get("bed_temp"),
            extruder_temp=self._bamboo_status.get("temps", {}).get("nozzle_temp"),
            last_updated=datetime.now()
        )

        self._cache[printer_id] = status
        return status

    def _init_bamboo_mqtt(self) -> None:
        """Initialize MQTT client for Bamboo H2D."""
        mqtt_host = self.settings.bamboo_mqtt_host or self.settings.bamboo_ip
        mqtt_port = self.settings.bamboo_mqtt_port

        self._bamboo_mqtt = mqtt.Client(
            client_id=f"kitty-status-{self.settings.bamboo_serial}",
            protocol=mqtt.MQTTv311
        )
        self._bamboo_mqtt.username_pw_set("bblp", self.settings.bamboo_access_code)
        self._bamboo_mqtt.on_message = self._on_bamboo_message

        # Enable TLS for port 8883 (Bambu LAN mode uses TLS with self-signed certs)
        if mqtt_port == 8883:
            self._bamboo_mqtt.tls_set(cert_reqs=ssl.CERT_NONE)
            self._bamboo_mqtt.tls_insecure_set(True)

        try:
            self._bamboo_mqtt.connect(mqtt_host, mqtt_port, keepalive=60)
            self._bamboo_mqtt.subscribe(f"device/{self.settings.bamboo_serial}/report")
            self._bamboo_mqtt.loop_start()
            LOGGER.info("Connected to Bamboo MQTT", host=mqtt_host, port=mqtt_port, tls=mqtt_port == 8883)
        except Exception as e:
            LOGGER.error("Failed to connect to Bamboo MQTT", error=str(e))

    def _on_bamboo_message(self, client, userdata, message):
        """Parse Bamboo MQTT status update."""
        try:
            self._bamboo_status = json.loads(message.payload.decode("utf-8"))
        except Exception as e:
            LOGGER.error("Failed to parse Bamboo MQTT message", error=str(e))

    async def get_elegoo_status(self) -> PrinterStatus:
        """
        Check Elegoo Giga status via Moonraker HTTP.

        Returns cached status if fresh (<30s old).
        Queries full thermal data including bed/nozzle temps and targets.
        """
        printer_id = "elegoo_giga"

        # Check cache
        if printer_id in self._cache:
            cached = self._cache[printer_id]
            age = datetime.now() - (cached.last_updated or datetime.min)
            if age < self._cache_ttl:
                LOGGER.debug("Using cached Elegoo status", age_seconds=age.total_seconds())
                return cached

        # Query Moonraker for full status including thermals
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Query printer objects for status, temps, and progress
                response = await client.get(
                    f"http://{self.settings.elegoo_ip}:{self.settings.elegoo_moonraker_port}"
                    f"/printer/objects/query?print_stats&heater_bed&extruder&virtual_sdcard"
                )
                response.raise_for_status()
                result = response.json().get("result", {})
                data = result.get("status", {})

                # Extract print state
                print_stats = data.get("print_stats", {})
                state = print_stats.get("state", "standby")
                is_printing = state == "printing"

                # Map Klipper states to our status strings
                state_map = {
                    "standby": "idle",
                    "printing": "printing",
                    "paused": "paused",
                    "complete": "idle",
                    "cancelled": "idle",
                    "error": "error",
                }
                status_str = state_map.get(state, "idle")

                # Extract thermal data
                heater_bed = data.get("heater_bed", {})
                extruder = data.get("extruder", {})
                virtual_sd = data.get("virtual_sdcard", {})

                # Calculate progress (Moonraker returns 0.0-1.0, we want 0-100)
                progress = virtual_sd.get("progress", 0)
                progress_percent = round(progress * 100, 1) if progress else None

                # Get current job filename
                current_job = print_stats.get("filename") if is_printing else None

                status = PrinterStatus(
                    printer_id=printer_id,
                    is_online=True,
                    is_printing=is_printing,
                    status=status_str,
                    current_job=current_job,
                    progress_percent=progress_percent,
                    bed_temp=heater_bed.get("temperature"),
                    bed_target=heater_bed.get("target"),
                    extruder_temp=extruder.get("temperature"),
                    extruder_target=extruder.get("target"),
                    last_updated=datetime.now()
                )

        except Exception as e:
            LOGGER.warning("Failed to get Elegoo status", error=str(e))
            status = PrinterStatus(
                printer_id=printer_id,
                is_online=False,
                is_printing=False,
                status="offline",
                last_updated=datetime.now()
            )

        self._cache[printer_id] = status
        return status

    async def get_all_statuses(self) -> Dict[str, PrinterStatus]:
        """Get status of all printers concurrently."""
        bamboo, elegoo = await asyncio.gather(
            self.get_bamboo_status(),
            self.get_elegoo_status(),
            return_exceptions=True
        )

        return {
            "bamboo_h2d": bamboo if not isinstance(bamboo, Exception) else PrinterStatus("bamboo_h2d", False, False, "offline"),
            "elegoo_giga": elegoo if not isinstance(elegoo, Exception) else PrinterStatus("elegoo_giga", False, False, "offline")
        }
