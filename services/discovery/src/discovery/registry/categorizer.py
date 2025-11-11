"""
Device categorization utilities.

Provides functions to classify unknown devices based on various heuristics:
- Port fingerprinting
- MAC address OUI lookup
- Hostname patterns
- Service detection
"""
import logging
import re
from typing import Optional, Tuple

try:
    from mac_vendor_lookup import MacLookup
except ImportError:
    MacLookup = None

from ..scanners.base import DeviceType

logger = logging.getLogger(__name__)


class DeviceCategorizer:
    """
    Utility class for device type classification.

    Uses multiple heuristics to identify device types from limited information.
    """

    def __init__(self):
        """Initialize categorizer."""
        # Initialize MAC vendor lookup (if available)
        self.mac_lookup = None
        if MacLookup:
            try:
                self.mac_lookup = MacLookup()
                # Update vendor database on first init
                self.mac_lookup.update_vendors()
            except Exception as e:
                logger.warning(f"Failed to initialize MAC vendor lookup: {e}")

    def categorize_by_port(self, port: int) -> Tuple[DeviceType, float]:
        """
        Classify device based on open port.

        Args:
            port: Open TCP port

        Returns:
            Tuple of (DeviceType, confidence_score)
        """
        # Well-known port mappings
        port_map = {
            5000: (DeviceType.OCTOPRINT, 0.85),
            7125: (DeviceType.PRINTER_3D, 0.85),  # Moonraker
            8123: (DeviceType.HOMEASSISTANT, 0.90),
            8888: (DeviceType.PRINTER_CNC, 0.70),  # Snapmaker
            9100: (DeviceType.PRINTER_3D, 0.60),  # Raw printing
        }

        return port_map.get(port, (DeviceType.UNKNOWN, 0.30))

    def categorize_by_hostname(self, hostname: str) -> Tuple[DeviceType, Optional[str], float]:
        """
        Classify device based on hostname.

        Args:
            hostname: Device hostname

        Returns:
            Tuple of (DeviceType, manufacturer, confidence_score)
        """
        hostname_lower = hostname.lower()

        # Printer patterns
        if "octoprint" in hostname_lower or "octopi" in hostname_lower:
            return DeviceType.OCTOPRINT, None, 0.90

        if "bamboo" in hostname_lower or "bambu" in hostname_lower:
            return DeviceType.PRINTER_3D, "Bamboo Labs", 0.85

        if "elegoo" in hostname_lower:
            return DeviceType.PRINTER_3D, "Elegoo", 0.85

        if "snapmaker" in hostname_lower:
            return DeviceType.PRINTER_CNC, "Snapmaker", 0.85

        if "prusa" in hostname_lower:
            return DeviceType.PRINTER_3D, "Prusa Research", 0.85

        if "ender" in hostname_lower or "creality" in hostname_lower:
            return DeviceType.PRINTER_3D, "Creality", 0.80

        # SBC patterns
        if "raspberrypi" in hostname_lower or "raspberry" in hostname_lower or "pi" in hostname_lower:
            # Check if it's hyphenated (e.g., "raspberry-pi-1")
            if re.match(r".*raspberry.*pi.*", hostname_lower) or hostname_lower.startswith("pi"):
                return DeviceType.RASPBERRY_PI, "Raspberry Pi Foundation", 0.80

        # ESP patterns
        if "esp32" in hostname_lower:
            return DeviceType.ESP32, "Espressif", 0.85

        if "esp8266" in hostname_lower:
            return DeviceType.ESP8266, "Espressif", 0.85

        # Arduino patterns
        if "arduino" in hostname_lower:
            return DeviceType.ARDUINO, "Arduino", 0.85

        # Home automation
        if "homeassistant" in hostname_lower or "hass" in hostname_lower:
            return DeviceType.HOMEASSISTANT, None, 0.90

        # Generic patterns
        if "printer" in hostname_lower:
            return DeviceType.PRINTER_3D, None, 0.60

        if "camera" in hostname_lower or "cam" in hostname_lower:
            return DeviceType.SMART_CAMERA, None, 0.70

        return DeviceType.UNKNOWN, None, 0.20

    def categorize_by_mac(self, mac_address: str) -> Tuple[DeviceType, Optional[str], float]:
        """
        Classify device based on MAC address (OUI lookup).

        Args:
            mac_address: Device MAC address

        Returns:
            Tuple of (DeviceType, manufacturer, confidence_score)
        """
        if not self.mac_lookup or not mac_address:
            return DeviceType.UNKNOWN, None, 0.10

        try:
            vendor = self.mac_lookup.lookup(mac_address)
            vendor_lower = vendor.lower()

            # Check known manufacturers
            if "espressif" in vendor_lower:
                # Likely ESP32/ESP8266, but can't distinguish without more info
                return DeviceType.ESP32, "Espressif", 0.70

            if "raspberry" in vendor_lower:
                return DeviceType.RASPBERRY_PI, "Raspberry Pi Foundation", 0.85

            if "arduino" in vendor_lower:
                return DeviceType.ARDUINO, "Arduino", 0.80

            # Generic IoT vendors
            if any(iot in vendor_lower for iot in ["tp-link", "shelly", "sonoff", "tuya"]):
                return DeviceType.SMART_PLUG, vendor, 0.60

            # Camera vendors
            if any(cam in vendor_lower for cam in ["hikvision", "dahua", "axis", "ubiquiti"]):
                return DeviceType.SMART_CAMERA, vendor, 0.70

            # Return vendor name but unknown type
            return DeviceType.UNKNOWN, vendor, 0.40

        except Exception as e:
            logger.debug(f"MAC vendor lookup failed: {e}")
            return DeviceType.UNKNOWN, None, 0.10

    def categorize_by_services(
        self, services: list
    ) -> Tuple[DeviceType, float]:
        """
        Classify device based on advertised services.

        Args:
            services: List of ServiceInfo objects

        Returns:
            Tuple of (DeviceType, confidence_score)
        """
        if not services:
            return DeviceType.UNKNOWN, 0.20

        # Check protocols
        protocols = [s.get("protocol", "") for s in services]
        ports = [s.get("port", 0) for s in services]

        # OctoPrint signature
        if 5000 in ports and "http" in protocols:
            return DeviceType.OCTOPRINT, 0.80

        # Moonraker/Klipper signature
        if 7125 in ports:
            return DeviceType.PRINTER_3D, 0.80

        # MQTT + HTTP might be a printer or smart device
        if "mqtt" in protocols and "http" in protocols:
            return DeviceType.UNKNOWN, 0.50  # Ambiguous

        # SSH might be SBC
        if "ssh" in protocols:
            return DeviceType.RASPBERRY_PI, 0.40  # Low confidence

        return DeviceType.UNKNOWN, 0.30

    def categorize_combined(
        self,
        hostname: Optional[str] = None,
        mac_address: Optional[str] = None,
        open_ports: Optional[list] = None,
        services: Optional[list] = None
    ) -> Tuple[DeviceType, Optional[str], float]:
        """
        Classify device using all available information.

        Combines multiple heuristics and returns the highest confidence result.

        Args:
            hostname: Device hostname
            mac_address: Device MAC address
            open_ports: List of open TCP ports
            services: List of advertised services

        Returns:
            Tuple of (DeviceType, manufacturer, confidence_score)
        """
        candidates = []

        # Try hostname
        if hostname:
            device_type, manufacturer, confidence = self.categorize_by_hostname(hostname)
            candidates.append((device_type, manufacturer, confidence))

        # Try MAC address
        if mac_address:
            device_type, manufacturer, confidence = self.categorize_by_mac(mac_address)
            candidates.append((device_type, manufacturer, confidence))

        # Try ports
        if open_ports:
            for port in open_ports:
                device_type, confidence = self.categorize_by_port(port)
                candidates.append((device_type, None, confidence))

        # Try services
        if services:
            device_type, confidence = self.categorize_by_services(services)
            candidates.append((device_type, None, confidence))

        # Select highest confidence result
        if candidates:
            best = max(candidates, key=lambda x: x[2])
            return best

        return DeviceType.UNKNOWN, None, 0.10
