"""
Base scanner interface for network discovery.

All discovery scanners inherit from BaseScanner and implement the scan() method.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class DeviceType(str, Enum):
    """Device type enumeration."""
    PRINTER_3D = "printer_3d"
    PRINTER_LASER = "printer_laser"
    PRINTER_CNC = "printer_cnc"
    RASPBERRY_PI = "raspberry_pi"
    ESP32 = "esp32"
    ESP8266 = "esp8266"
    ARDUINO = "arduino"
    SMART_PLUG = "smart_plug"
    SMART_CAMERA = "smart_camera"
    SMART_SENSOR = "smart_sensor"
    OCTOPRINT = "octoprint"
    HOMEASSISTANT = "homeassistant"
    UNKNOWN = "unknown"


class DiscoveryMethod(str, Enum):
    """Discovery method enumeration."""
    MDNS = "mdns"
    SSDP = "ssdp"
    BAMBOO_UDP = "bamboo_udp"
    SNAPMAKER_UDP = "snapmaker_udp"
    NMAP = "nmap"
    ARP = "arp"


@dataclass
class ServiceInfo:
    """Information about a discovered service."""
    protocol: str  # http, mqtt, ssh, etc.
    port: int
    name: str
    version: Optional[str] = None


@dataclass
class DiscoveredDevice:
    """Discovered device information."""
    # Discovery metadata
    discovered_at: datetime
    discovery_method: DiscoveryMethod

    # Network information
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None

    # Device identification
    device_type: DeviceType = DeviceType.UNKNOWN
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None

    # Service information
    services: List[ServiceInfo] = None
    capabilities: Dict[str, Any] = None

    # Confidence score (0.0-1.0)
    confidence_score: float = 0.5

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.services is None:
            self.services = []
        if self.capabilities is None:
            self.capabilities = {}


class ScanResult:
    """Result of a discovery scan."""

    def __init__(self, scanner_name: str):
        self.scanner_name = scanner_name
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.devices: List[DiscoveredDevice] = []
        self.errors: List[str] = []
        self.success = False

    def add_device(self, device: DiscoveredDevice) -> None:
        """Add discovered device to results."""
        self.devices.append(device)

    def add_error(self, error: str) -> None:
        """Add error message to results."""
        self.errors.append(error)

    def complete(self, success: bool = True) -> None:
        """Mark scan as completed."""
        self.completed_at = datetime.utcnow()
        self.success = success

    @property
    def duration_seconds(self) -> float:
        """Scan duration in seconds."""
        if self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return 0.0


class BaseScanner(ABC):
    """
    Abstract base class for network discovery scanners.

    All scanners must implement the scan() method which returns a ScanResult.
    """

    def __init__(self, timeout_seconds: int = 10):
        """
        Initialize scanner.

        Args:
            timeout_seconds: Maximum time to wait for responses
        """
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def name(self) -> str:
        """Scanner name (e.g., 'mDNS', 'SSDP')."""
        pass

    @property
    @abstractmethod
    def discovery_method(self) -> DiscoveryMethod:
        """Discovery method enum value."""
        pass

    @abstractmethod
    async def scan(self) -> ScanResult:
        """
        Execute discovery scan.

        Returns:
            ScanResult with discovered devices and any errors
        """
        pass

    def _create_device(
        self,
        ip_address: str,
        hostname: Optional[str] = None,
        device_type: DeviceType = DeviceType.UNKNOWN,
        confidence_score: float = 0.5,
        **kwargs
    ) -> DiscoveredDevice:
        """
        Helper to create DiscoveredDevice with common fields.

        Args:
            ip_address: Device IP address
            hostname: Optional hostname
            device_type: Device type classification
            confidence_score: Confidence in classification (0.0-1.0)
            **kwargs: Additional fields for DiscoveredDevice

        Returns:
            DiscoveredDevice instance
        """
        return DiscoveredDevice(
            discovered_at=datetime.utcnow(),
            discovery_method=self.discovery_method,
            ip_address=ip_address,
            hostname=hostname,
            device_type=device_type,
            confidence_score=confidence_score,
            **kwargs
        )
