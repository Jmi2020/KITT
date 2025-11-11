"""
mDNS/Bonjour discovery scanner.

Discovers devices advertising services via Bonjour/mDNS (zeroconf).
Targets printers, OctoPrint, Klipper Moonraker, SSH servers (Raspberry Pi), etc.
"""
import asyncio
import logging
from typing import List

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

from .base import (
    BaseScanner,
    DeviceType,
    DiscoveredDevice,
    DiscoveryMethod,
    ScanResult,
    ServiceInfo as DiscoveredServiceInfo,
)

logger = logging.getLogger(__name__)


# Service types to search for
MDNS_SERVICE_TYPES = [
    "_http._tcp.local.",
    "_printer._tcp.local.",
    "_ipp._tcp.local.",
    "_octoprint._tcp.local.",
    "_moonraker._tcp.local.",
    "_ssh._tcp.local.",
    "_mqtt._tcp.local.",
    "_homeassistant._tcp.local.",
]


class MDNSScanner(BaseScanner):
    """
    mDNS/Bonjour scanner using zeroconf library.

    Discovers devices advertising services via Bonjour/mDNS protocol.
    """

    def __init__(self, timeout_seconds: int = 5):
        """
        Initialize mDNS scanner.

        Args:
            timeout_seconds: How long to listen for mDNS responses
        """
        super().__init__(timeout_seconds)
        self._discovered_services: List[ServiceInfo] = []

    @property
    def name(self) -> str:
        return "mDNS/Bonjour"

    @property
    def discovery_method(self) -> DiscoveryMethod:
        return DiscoveryMethod.MDNS

    async def scan(self) -> ScanResult:
        """
        Execute mDNS discovery scan.

        Returns:
            ScanResult with discovered devices
        """
        result = ScanResult(scanner_name=self.name)

        try:
            logger.info(f"Starting mDNS scan (timeout={self.timeout_seconds}s)")

            # Use AsyncZeroconf for async operation
            aiozc = AsyncZeroconf()
            zc = aiozc.zeroconf

            # Browse for each service type
            browsers = []
            for service_type in MDNS_SERVICE_TYPES:
                browser = ServiceBrowser(
                    zc,
                    service_type,
                    handlers=[self._on_service_state_change]
                )
                browsers.append(browser)

            # Wait for responses
            await asyncio.sleep(self.timeout_seconds)

            # Process discovered services
            devices = await self._process_discovered_services(zc)
            for device in devices:
                result.add_device(device)

            # Cleanup
            for browser in browsers:
                browser.cancel()
            await aiozc.async_close()

            result.complete(success=True)
            logger.info(f"mDNS scan completed: {len(result.devices)} devices found")

        except Exception as e:
            logger.error(f"mDNS scan failed: {e}", exc_info=True)
            result.add_error(str(e))
            result.complete(success=False)

        return result

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change
    ) -> None:
        """
        Callback for service state changes.

        Args:
            zeroconf: Zeroconf instance
            service_type: Service type (e.g., "_http._tcp.local.")
            name: Service name
            state_change: State change type
        """
        # Get service info
        info = zeroconf.get_service_info(service_type, name)
        if info:
            self._discovered_services.append(info)

    async def _process_discovered_services(
        self, zeroconf: Zeroconf
    ) -> List[DiscoveredDevice]:
        """
        Process discovered mDNS services into DiscoveredDevice objects.

        Args:
            zeroconf: Zeroconf instance for querying service info

        Returns:
            List of DiscoveredDevice objects
        """
        devices = []
        seen_ips = set()  # Deduplicate by IP address

        for service_info in self._discovered_services:
            try:
                # Extract IP address
                if not service_info.addresses:
                    continue

                ip_address = ".".join(str(b) for b in service_info.addresses[0])

                # Skip duplicates
                if ip_address in seen_ips:
                    continue
                seen_ips.add(ip_address)

                # Extract hostname
                hostname = service_info.server.rstrip(".")

                # Extract service information
                service_type = service_info.type.rstrip(".")
                port = service_info.port
                service_name = service_info.name

                # Classify device based on service type
                device_type, manufacturer, confidence = self._classify_device(
                    service_type, service_name, service_info.properties
                )

                # Build services list
                services = [
                    DiscoveredServiceInfo(
                        protocol=self._protocol_from_service_type(service_type),
                        port=port,
                        name=service_name,
                        version=self._extract_version(service_info.properties)
                    )
                ]

                # Extract additional properties
                properties = {
                    k.decode("utf-8") if isinstance(k, bytes) else k:
                    v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in service_info.properties.items()
                }

                # Create device
                device = self._create_device(
                    ip_address=ip_address,
                    hostname=hostname,
                    device_type=device_type,
                    manufacturer=manufacturer,
                    confidence_score=confidence,
                    services=services,
                    capabilities={"mdns_properties": properties}
                )

                devices.append(device)

            except Exception as e:
                logger.warning(f"Failed to process mDNS service: {e}")

        return devices

    def _classify_device(
        self, service_type: str, service_name: str, properties: dict
    ) -> tuple:
        """
        Classify device based on mDNS service type and properties.

        Args:
            service_type: mDNS service type (e.g., "_http._tcp.local.")
            service_name: Service name
            properties: Service properties dict

        Returns:
            Tuple of (DeviceType, manufacturer, confidence_score)
        """
        service_lower = service_type.lower()
        name_lower = service_name.lower()

        # OctoPrint
        if "_octoprint" in service_lower or "octoprint" in name_lower:
            return DeviceType.OCTOPRINT, None, 0.95

        # Klipper Moonraker (3D printer)
        if "_moonraker" in service_lower or "moonraker" in name_lower:
            return DeviceType.PRINTER_3D, "Klipper", 0.90

        # Home Assistant
        if "_homeassistant" in service_lower or "homeassistant" in name_lower:
            return DeviceType.HOMEASSISTANT, None, 0.95

        # Generic printer services
        if "_printer" in service_lower or "_ipp" in service_lower:
            return DeviceType.PRINTER_3D, None, 0.70

        # SSH services - check for Raspberry Pi
        if "_ssh" in service_lower:
            if "raspberry" in name_lower or "raspberrypi" in name_lower:
                return DeviceType.RASPBERRY_PI, "Raspberry Pi Foundation", 0.85
            # Generic SSH server
            return DeviceType.UNKNOWN, None, 0.30

        # HTTP services - low confidence without more info
        if "_http" in service_lower:
            # Check service name for hints
            if "bambu" in name_lower:
                return DeviceType.PRINTER_3D, "Bamboo Labs", 0.80
            if "elegoo" in name_lower:
                return DeviceType.PRINTER_3D, "Elegoo", 0.80
            if "snapmaker" in name_lower:
                return DeviceType.PRINTER_CNC, "Snapmaker", 0.80
            if "esp32" in name_lower:
                return DeviceType.ESP32, "Espressif", 0.75
            if "esp8266" in name_lower:
                return DeviceType.ESP8266, "Espressif", 0.75

            return DeviceType.UNKNOWN, None, 0.40

        # MQTT broker
        if "_mqtt" in service_lower:
            return DeviceType.UNKNOWN, None, 0.50

        # Default: unknown
        return DeviceType.UNKNOWN, None, 0.30

    def _protocol_from_service_type(self, service_type: str) -> str:
        """
        Extract protocol name from mDNS service type.

        Args:
            service_type: mDNS service type (e.g., "_http._tcp.local.")

        Returns:
            Protocol name (e.g., "http", "ssh")
        """
        # Remove leading underscore and trailing domain
        parts = service_type.split(".")
        if parts and parts[0].startswith("_"):
            return parts[0][1:]  # Remove leading underscore
        return "unknown"

    def _extract_version(self, properties: dict) -> str:
        """
        Extract version from mDNS service properties.

        Args:
            properties: Service properties dict

        Returns:
            Version string or None
        """
        version_keys = ["version", "ver", "v", "sw_version", "firmware"]
        for key in version_keys:
            # Try both string and byte keys
            for prop_key in [key, key.encode("utf-8")]:
                if prop_key in properties:
                    value = properties[prop_key]
                    if isinstance(value, bytes):
                        return value.decode("utf-8")
                    return str(value)
        return None
