"""Moonraker API driver for Klipper-based printers (Elegoo Giga, Snapmaker Artisan).

Moonraker is the REST API server for Klipper firmware. This driver provides
automated print control for any Klipper-based 3D printer.

API Documentation: https://moonraker.readthedocs.io/en/latest/web_api/
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx

from common.logging import get_logger

from .base import (
    PrinterCapabilities,
    PrinterDriver,
    PrinterState,
    PrinterStatus,
)

LOGGER = get_logger(__name__)


class MoonrakerDriver(PrinterDriver):
    """Moonraker API driver for Klipper printers.

    Supports:
    - Elegoo OrangeStorm Giga (Klipper + Moonraker)
    - Snapmaker Artisan (Klipper + Moonraker)
    - Any Klipper printer with Moonraker API

    Configuration:
    {
        "base_url": "http://elegoo-giga.local:7125",
        "api_key": "optional_api_key",  # If authentication enabled
        "timeout": 30,  # Request timeout in seconds
    }
    """

    def __init__(self, printer_id: str, config: dict):
        """Initialize Moonraker driver.

        Args:
            printer_id: Unique printer identifier
            config: Driver configuration with base_url, api_key, timeout
        """
        super().__init__(printer_id, config)

        self.base_url = config["base_url"].rstrip("/")
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 30)

        # HTTP client
        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        )

        self._connected = False

    async def connect(self) -> bool:
        """Establish connection to Moonraker API.

        Returns:
            True if Moonraker is responsive
        """
        try:
            # Test connection with server info request
            response = await self.client.get("/server/info")
            response.raise_for_status()

            server_info = response.json()
            LOGGER.info(
                "Connected to Moonraker",
                printer_id=self.printer_id,
                klippy_version=server_info.get("result", {}).get("klippy_version"),
            )

            self._connected = True
            return True

        except Exception as e:
            LOGGER.error(
                "Failed to connect to Moonraker",
                printer_id=self.printer_id,
                base_url=self.base_url,
                error=str(e),
            )
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close connection to Moonraker."""
        await self.client.aclose()
        self._connected = False
        LOGGER.info("Disconnected from Moonraker", printer_id=self.printer_id)

    async def is_connected(self) -> bool:
        """Check if driver is connected to Moonraker.

        Returns:
            True if connected and responsive
        """
        if not self._connected:
            return False

        try:
            response = await self.client.get("/server/info")
            return response.status_code == 200
        except Exception:
            return False

    async def get_status(self) -> PrinterStatus:
        """Get current printer status.

        Returns:
            Current printer status snapshot
        """
        try:
            # Query printer objects for comprehensive status
            # https://moonraker.readthedocs.io/en/latest/web_api/#query-printer-object-status
            objects = "print_stats,toolhead,heater_bed,extruder,display_status,virtual_sdcard"
            response = await self.client.get(
                f"/printer/objects/query?{objects}"
            )
            response.raise_for_status()

            data = response.json()["result"]["status"]

            # Extract print_stats
            print_stats = data.get("print_stats", {})
            state_str = print_stats.get("state", "unknown")

            # Map Klipper state to our PrinterState
            state_map = {
                "standby": PrinterState.standby,
                "printing": PrinterState.printing,
                "paused": PrinterState.paused,
                "complete": PrinterState.complete,
                "cancelled": PrinterState.idle,
                "error": PrinterState.error,
            }
            state = state_map.get(state_str, PrinterState.offline)

            # Extract temperatures
            heater_bed = data.get("heater_bed", {})
            extruder = data.get("extruder", {})

            # Extract print progress
            virtual_sdcard = data.get("virtual_sdcard", {})
            display_status = data.get("display_status", {})

            progress_percent = virtual_sdcard.get("progress", 0) * 100
            current_file = print_stats.get("filename")

            return PrinterStatus(
                printer_id=self.printer_id,
                state=state,
                is_online=True,
                is_printing=(state == PrinterState.printing),
                nozzle_temp=extruder.get("temperature"),
                nozzle_target=extruder.get("target"),
                bed_temp=heater_bed.get("temperature"),
                bed_target=heater_bed.get("target"),
                current_file=current_file,
                progress_percent=progress_percent if current_file else None,
                print_duration_seconds=int(print_stats.get("print_duration", 0)),
                error_message=print_stats.get("message") if state == PrinterState.error else None,
            )

        except Exception as e:
            LOGGER.error(
                "Failed to get printer status",
                printer_id=self.printer_id,
                error=str(e),
                exc_info=True,
            )
            return PrinterStatus(
                printer_id=self.printer_id,
                state=PrinterState.offline,
                is_online=False,
                is_printing=False,
                error_message=f"Failed to query status: {str(e)}",
            )

    async def get_capabilities(self) -> PrinterCapabilities:
        """Get printer hardware capabilities.

        Note: Moonraker doesn't expose build volume via API,
        so we use hardcoded values based on printer_id.

        Returns:
            Printer capabilities
        """
        # Hardcoded build volumes for known printers
        build_volumes = {
            "elegoo_giga": (800, 800, 1000),  # 800x800x1000mm
            "snapmaker_artisan": (400, 400, 400),  # 400x400x400mm
        }

        x, y, z = build_volumes.get(self.printer_id, (200, 200, 200))

        return PrinterCapabilities(
            printer_id=self.printer_id,
            printer_type=self.printer_id,
            build_volume_x=x,
            build_volume_y=y,
            build_volume_z=z,
            has_camera=True,  # Both have cameras via Raspberry Pi
            has_auto_leveling=True,  # Klipper supports bed mesh
            supports_multi_color=False,
            supports_resume=True,  # Klipper supports resume after power loss
            supported_materials=["PLA", "PETG", "ABS", "TPU"],
        )

    async def upload_gcode(self, gcode_path: str, filename: Optional[str] = None) -> str:
        """Upload G-code file to printer.

        Args:
            gcode_path: Local path to G-code file
            filename: Optional filename on printer (defaults to basename)

        Returns:
            Remote filename on printer

        Raises:
            FileNotFoundError: If gcode_path doesn't exist
            ConnectionError: If upload fails
        """
        gcode_file = Path(gcode_path)
        if not gcode_file.exists():
            raise FileNotFoundError(f"G-code file not found: {gcode_path}")

        if filename is None:
            filename = gcode_file.name

        try:
            # Upload to virtual SD card (gcodes directory)
            # https://moonraker.readthedocs.io/en/latest/web_api/#upload-a-file
            with open(gcode_file, "rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                response = await self.client.post(
                    "/server/files/upload",
                    files=files,
                )
                response.raise_for_status()

            result = response.json()["result"]
            uploaded_filename = result.get("item", {}).get("path", filename)

            LOGGER.info(
                "Uploaded G-code to printer",
                printer_id=self.printer_id,
                filename=uploaded_filename,
                size_bytes=gcode_file.stat().st_size,
            )

            return uploaded_filename

        except Exception as e:
            LOGGER.error(
                "Failed to upload G-code",
                printer_id=self.printer_id,
                filename=filename,
                error=str(e),
                exc_info=True,
            )
            raise ConnectionError(f"Failed to upload G-code: {str(e)}")

    async def start_print(self, filename: str) -> bool:
        """Start printing a file.

        Args:
            filename: Filename on printer to print (in gcodes/ directory)

        Returns:
            True if print started successfully
        """
        try:
            # Start print via POST /printer/print/start
            # https://moonraker.readthedocs.io/en/latest/web_api/#start-a-print
            response = await self.client.post(
                "/printer/print/start",
                json={"filename": filename},
            )
            response.raise_for_status()

            LOGGER.info(
                "Started print",
                printer_id=self.printer_id,
                filename=filename,
            )
            return True

        except Exception as e:
            LOGGER.error(
                "Failed to start print",
                printer_id=self.printer_id,
                filename=filename,
                error=str(e),
                exc_info=True,
            )
            return False

    async def pause_print(self) -> bool:
        """Pause current print."""
        try:
            response = await self.client.post("/printer/print/pause")
            response.raise_for_status()

            LOGGER.info("Paused print", printer_id=self.printer_id)
            return True

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
            response = await self.client.post("/printer/print/resume")
            response.raise_for_status()

            LOGGER.info("Resumed print", printer_id=self.printer_id)
            return True

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
            response = await self.client.post("/printer/print/cancel")
            response.raise_for_status()

            LOGGER.info("Cancelled print", printer_id=self.printer_id)
            return True

        except Exception as e:
            LOGGER.error(
                "Failed to cancel print",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False

    async def set_bed_temperature(self, temp_celsius: float) -> bool:
        """Set bed target temperature."""
        try:
            # Send G-code command M140 (set bed temp, don't wait)
            gcode = f"M140 S{temp_celsius}"
            response = await self.client.post(
                "/printer/gcode/script",
                json={"script": gcode},
            )
            response.raise_for_status()

            LOGGER.info(
                "Set bed temperature",
                printer_id=self.printer_id,
                temp_celsius=temp_celsius,
            )
            return True

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
            # Send G-code command M104 (set extruder temp, don't wait)
            gcode = f"M104 S{temp_celsius}"
            response = await self.client.post(
                "/printer/gcode/script",
                json={"script": gcode},
            )
            response.raise_for_status()

            LOGGER.info(
                "Set nozzle temperature",
                printer_id=self.printer_id,
                temp_celsius=temp_celsius,
            )
            return True

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

            gcode = f"G28{axes}"
            response = await self.client.post(
                "/printer/gcode/script",
                json={"script": gcode},
            )
            response.raise_for_status()

            LOGGER.info(
                "Homing axes",
                printer_id=self.printer_id,
                axes=axes.strip(),
            )
            return True

        except Exception as e:
            LOGGER.error(
                "Failed to home axes",
                printer_id=self.printer_id,
                error=str(e),
            )
            return False
