"""Base printer driver interface.

All printer drivers (Moonraker, Bamboo MQTT, etc.) implement this interface
to provide consistent control across different printer types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PrinterState(str, Enum):
    """Printer operational state."""

    offline = "offline"
    idle = "idle"
    printing = "printing"
    paused = "paused"
    complete = "complete"
    error = "error"
    standby = "standby"


@dataclass
class PrinterStatus:
    """Current printer status snapshot."""

    printer_id: str
    state: PrinterState
    is_online: bool
    is_printing: bool

    # Temperature sensors
    nozzle_temp: Optional[float] = None
    nozzle_target: Optional[float] = None
    bed_temp: Optional[float] = None
    bed_target: Optional[float] = None

    # Print progress (if printing)
    current_file: Optional[str] = None
    progress_percent: Optional[float] = None
    print_duration_seconds: Optional[int] = None
    time_remaining_seconds: Optional[int] = None

    # Current layer info (if available)
    current_layer: Optional[int] = None
    total_layers: Optional[int] = None

    # Error information
    error_message: Optional[str] = None

    # Timestamp
    updated_at: datetime = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


@dataclass
class PrinterCapabilities:
    """Printer hardware capabilities."""

    printer_id: str
    printer_type: str  # "bamboo_h2d", "elegoo_giga", "snapmaker_artisan"

    # Build volume (mm)
    build_volume_x: float
    build_volume_y: float
    build_volume_z: float

    # Supported features
    has_camera: bool = False
    has_auto_leveling: bool = False
    supports_multi_color: bool = False
    supports_resume: bool = False

    # Material support
    supported_materials: list[str] = None

    def __post_init__(self):
        if self.supported_materials is None:
            self.supported_materials = []


class PrinterDriver(ABC):
    """Abstract base class for printer drivers.

    All printer drivers must implement these methods to provide
    consistent control interface across different printer types.
    """

    def __init__(self, printer_id: str, config: dict):
        """Initialize printer driver.

        Args:
            printer_id: Unique printer identifier
            config: Driver-specific configuration
        """
        self.printer_id = printer_id
        self.config = config

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to printer.

        Returns:
            True if connected successfully, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to printer."""
        pass

    @abstractmethod
    async def get_status(self) -> PrinterStatus:
        """Get current printer status.

        Returns:
            Current printer status snapshot
        """
        pass

    @abstractmethod
    async def get_capabilities(self) -> PrinterCapabilities:
        """Get printer hardware capabilities.

        Returns:
            Printer capabilities and features
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def start_print(self, filename: str) -> bool:
        """Start printing a file.

        Args:
            filename: Filename on printer to print

        Returns:
            True if print started successfully

        Raises:
            ValueError: If printer busy or file doesn't exist
            ConnectionError: If command fails
        """
        pass

    @abstractmethod
    async def pause_print(self) -> bool:
        """Pause current print.

        Returns:
            True if paused successfully
        """
        pass

    @abstractmethod
    async def resume_print(self) -> bool:
        """Resume paused print.

        Returns:
            True if resumed successfully
        """
        pass

    @abstractmethod
    async def cancel_print(self) -> bool:
        """Cancel current print.

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    async def set_bed_temperature(self, temp_celsius: float) -> bool:
        """Set bed target temperature.

        Args:
            temp_celsius: Target temperature in Celsius

        Returns:
            True if command accepted
        """
        pass

    @abstractmethod
    async def set_nozzle_temperature(self, temp_celsius: float) -> bool:
        """Set nozzle target temperature.

        Args:
            temp_celsius: Target temperature in Celsius

        Returns:
            True if command accepted
        """
        pass

    @abstractmethod
    async def home_axes(self, x: bool = True, y: bool = True, z: bool = True) -> bool:
        """Home printer axes.

        Args:
            x: Home X axis
            y: Home Y axis
            z: Home Z axis

        Returns:
            True if homing started
        """
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if driver is connected to printer.

        Returns:
            True if connected and responsive
        """
        pass
