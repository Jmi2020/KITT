"""Check printer availability via MQTT and HTTP."""

from __future__ import annotations

import asyncio
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
    extruder_temp: Optional[float] = None
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

        try:
            self._bamboo_mqtt.connect(mqtt_host, mqtt_port, keepalive=60)
            self._bamboo_mqtt.subscribe(f"device/{self.settings.bamboo_serial}/report")
            self._bamboo_mqtt.loop_start()
            LOGGER.info("Connected to Bamboo MQTT", host=mqtt_host, port=mqtt_port)
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
        """
        printer_id = "elegoo_giga"

        # Check cache
        if printer_id in self._cache:
            cached = self._cache[printer_id]
            age = datetime.now() - (cached.last_updated or datetime.min)
            if age < self._cache_ttl:
                LOGGER.debug("Using cached Elegoo status", age_seconds=age.total_seconds())
                return cached

        # Query Moonraker
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(
                    f"http://{self.settings.elegoo_ip}:{self.settings.elegoo_moonraker_port}/printer/info"
                )
                response.raise_for_status()
                data = response.json()

                state = data.get("result", {}).get("state", "offline")
                is_printing = state == "printing"

                status = PrinterStatus(
                    printer_id=printer_id,
                    is_online=True,
                    is_printing=is_printing,
                    status="printing" if is_printing else "idle",
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
