"""
SSDP/UPnP discovery scanner.

Discovers UPnP-enabled devices via SSDP (Simple Service Discovery Protocol).
Targets smart home devices, cameras, network printers with UPnP support.
"""
import asyncio
import logging
from typing import List
from urllib.parse import urlparse

import httpx
from ssdpy import SSDPClient

from .base import (
    BaseScanner,
    DeviceType,
    DiscoveredDevice,
    DiscoveryMethod,
    ScanResult,
    ServiceInfo as DiscoveredServiceInfo,
)

logger = logging.getLogger(__name__)


class SSDPScanner(BaseScanner):
    """
    SSDP/UPnP scanner using ssdpy library.

    Discovers UPnP-enabled devices via SSDP multicast discovery.
    """

    def __init__(self, timeout_seconds: int = 3):
        """
        Initialize SSDP scanner.

        Args:
            timeout_seconds: How long to wait for SSDP responses
        """
        super().__init__(timeout_seconds)

    @property
    def name(self) -> str:
        return "SSDP/UPnP"

    @property
    def discovery_method(self) -> DiscoveryMethod:
        return DiscoveryMethod.SSDP

    async def scan(self) -> ScanResult:
        """
        Execute SSDP discovery scan.

        Returns:
            ScanResult with discovered devices
        """
        result = ScanResult(scanner_name=self.name)

        try:
            logger.info(f"Starting SSDP scan (timeout={self.timeout_seconds}s)")

            # Run SSDP discovery in executor (blocking operation)
            devices = await asyncio.get_event_loop().run_in_executor(
                None, self._discover_ssdp_devices
            )

            for device in devices:
                result.add_device(device)

            result.complete(success=True)
            logger.info(f"SSDP scan completed: {len(result.devices)} devices found")

        except Exception as e:
            logger.error(f"SSDP scan failed: {e}", exc_info=True)
            result.add_error(str(e))
            result.complete(success=False)

        return result

    def _discover_ssdp_devices(self) -> List[DiscoveredDevice]:
        """
        Execute SSDP discovery (blocking operation).

        Returns:
            List of DiscoveredDevice objects
        """
        devices = []
        seen_locations = set()  # Deduplicate by location URL

        try:
            # Create SSDP client
            client = SSDPClient()

            # Discover all UPnP devices
            upnp_devices = client.m_search(
                service_type="ssdp:all",
                timeout=self.timeout_seconds
            )

            for device_data in upnp_devices:
                try:
                    # Extract location URL
                    location = device_data.get("location")
                    if not location or location in seen_locations:
                        continue
                    seen_locations.add(location)

                    # Parse location URL for IP and port
                    parsed_url = urlparse(location)
                    ip_address = parsed_url.hostname
                    port = parsed_url.port or 80

                    # Fetch device description XML
                    device_info = self._fetch_device_description(location)

                    # Classify device
                    device_type, manufacturer, model, confidence = self._classify_device(
                        device_data, device_info
                    )

                    # Extract hostname from server header or URL
                    hostname = device_data.get("server", parsed_url.hostname)

                    # Build services list
                    services = [
                        DiscoveredServiceInfo(
                            protocol="http",
                            port=port,
                            name="UPnP Service",
                            version=None
                        )
                    ]

                    # Create device
                    device = self._create_device(
                        ip_address=ip_address,
                        hostname=hostname,
                        device_type=device_type,
                        manufacturer=manufacturer,
                        model=model,
                        confidence_score=confidence,
                        services=services,
                        capabilities={
                            "upnp_location": location,
                            "upnp_server": device_data.get("server"),
                            "upnp_device_type": device_info.get("deviceType"),
                            "upnp_friendly_name": device_info.get("friendlyName"),
                        }
                    )

                    devices.append(device)

                except Exception as e:
                    logger.warning(f"Failed to process SSDP device: {e}")

        except Exception as e:
            logger.error(f"SSDP discovery failed: {e}")

        return devices

    def _fetch_device_description(self, location: str) -> dict:
        """
        Fetch UPnP device description XML and parse basic info.

        Args:
            location: Device description URL

        Returns:
            Dict with device info (friendlyName, manufacturer, model, etc.)
        """
        try:
            response = httpx.get(location, timeout=3.0)
            response.raise_for_status()

            # Parse XML (basic parsing - extract key fields)
            xml_content = response.text
            info = {}

            # Extract fields between tags (simple regex-free parsing)
            for field in ["friendlyName", "manufacturer", "modelName", "deviceType"]:
                start_tag = f"<{field}>"
                end_tag = f"</{field}>"
                start_idx = xml_content.find(start_tag)
                end_idx = xml_content.find(end_tag)

                if start_idx != -1 and end_idx != -1:
                    value = xml_content[start_idx + len(start_tag):end_idx].strip()
                    info[field] = value

            return info

        except Exception as e:
            logger.debug(f"Failed to fetch device description from {location}: {e}")
            return {}

    def _classify_device(
        self, device_data: dict, device_info: dict
    ) -> tuple:
        """
        Classify device based on SSDP headers and device description.

        Args:
            device_data: SSDP response headers
            device_info: Parsed device description XML

        Returns:
            Tuple of (DeviceType, manufacturer, model, confidence_score)
        """
        friendly_name = device_info.get("friendlyName", "").lower()
        manufacturer = device_info.get("manufacturer", "").lower()
        model = device_info.get("modelName", "")
        device_type_str = device_info.get("deviceType", "").lower()
        server = device_data.get("server", "").lower()

        # Manufacturer extraction
        manufacturer_name = None
        if manufacturer:
            manufacturer_name = device_info.get("manufacturer")

        # Classify by device type and name patterns
        if "printer" in device_type_str or "printer" in friendly_name:
            return DeviceType.PRINTER_3D, manufacturer_name, model, 0.75

        if "camera" in device_type_str or "camera" in friendly_name:
            return DeviceType.SMART_CAMERA, manufacturer_name, model, 0.85

        if "sensor" in device_type_str or "sensor" in friendly_name:
            return DeviceType.SMART_SENSOR, manufacturer_name, model, 0.80

        if "smartplug" in device_type_str.replace(" ", "") or "plug" in friendly_name:
            return DeviceType.SMART_PLUG, manufacturer_name, model, 0.85

        # Check for known manufacturers/models
        if "elegoo" in friendly_name or "elegoo" in manufacturer:
            return DeviceType.PRINTER_3D, "Elegoo", model, 0.80

        if "octoprint" in server or "octoprint" in friendly_name:
            return DeviceType.OCTOPRINT, manufacturer_name, model, 0.90

        if "homeassistant" in server or "homeassistant" in friendly_name:
            return DeviceType.HOMEASSISTANT, manufacturer_name, model, 0.90

        # ESP32/ESP8266 running UPnP
        if "esp32" in friendly_name or "esp32" in server:
            return DeviceType.ESP32, "Espressif", model, 0.75

        if "esp8266" in friendly_name or "esp8266" in server:
            return DeviceType.ESP8266, "Espressif", model, 0.75

        # Default: unknown UPnP device
        return DeviceType.UNKNOWN, manufacturer_name, model, 0.40
