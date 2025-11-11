"""
Bamboo Labs UDP discovery scanner.

Discovers Bamboo Labs 3D printers via UDP broadcast on port 2021.
Uses the M990 device info request command.
"""
import asyncio
import json
import logging
import socket
from typing import List, Optional

from .base import (
    BaseScanner,
    DeviceType,
    DiscoveredDevice,
    DiscoveryMethod,
    ScanResult,
    ServiceInfo as DiscoveredServiceInfo,
)

logger = logging.getLogger(__name__)


BAMBOO_DISCOVERY_PORT = 2021
BAMBOO_DISCOVERY_MESSAGE = b"M990"  # Device info request


class BambooScanner(BaseScanner):
    """
    Bamboo Labs printer discovery via UDP broadcast.

    Sends M990 command to port 2021 and listens for responses.
    """

    def __init__(self, timeout_seconds: int = 2):
        """
        Initialize Bamboo scanner.

        Args:
            timeout_seconds: How long to wait for UDP responses
        """
        super().__init__(timeout_seconds)

    @property
    def name(self) -> str:
        return "Bamboo Labs UDP"

    @property
    def discovery_method(self) -> DiscoveryMethod:
        return DiscoveryMethod.BAMBOO_UDP

    async def scan(self) -> ScanResult:
        """
        Execute Bamboo Labs UDP discovery scan.

        Returns:
            ScanResult with discovered Bamboo printers
        """
        result = ScanResult(scanner_name=self.name)

        try:
            logger.info(f"Starting Bamboo Labs UDP scan (timeout={self.timeout_seconds}s)")

            # Run UDP discovery
            devices = await self._discover_bamboo_printers()

            for device in devices:
                result.add_device(device)

            result.complete(success=True)
            logger.info(f"Bamboo Labs scan completed: {len(result.devices)} devices found")

        except Exception as e:
            logger.error(f"Bamboo Labs scan failed: {e}", exc_info=True)
            result.add_error(str(e))
            result.complete(success=False)

        return result

    async def _discover_bamboo_printers(self) -> List[DiscoveredDevice]:
        """
        Send UDP broadcast and collect Bamboo printer responses.

        Returns:
            List of DiscoveredDevice objects
        """
        devices = []

        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(self.timeout_seconds)

            # Send broadcast
            broadcast_addr = ("<broadcast>", BAMBOO_DISCOVERY_PORT)
            sock.sendto(BAMBOO_DISCOVERY_MESSAGE, broadcast_addr)

            # Collect responses
            start_time = asyncio.get_event_loop().time()
            while True:
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= self.timeout_seconds:
                    break

                try:
                    # Receive response
                    data, addr = sock.recvfrom(4096)
                    ip_address = addr[0]

                    # Parse response
                    device = self._parse_bamboo_response(data, ip_address)
                    if device:
                        devices.append(device)

                except socket.timeout:
                    break
                except Exception as e:
                    logger.debug(f"Error receiving Bamboo response: {e}")

            sock.close()

        except Exception as e:
            logger.error(f"Bamboo UDP discovery failed: {e}")

        return devices

    def _parse_bamboo_response(
        self, data: bytes, ip_address: str
    ) -> Optional[DiscoveredDevice]:
        """
        Parse Bamboo Labs UDP response.

        Args:
            data: UDP response data
            ip_address: Source IP address

        Returns:
            DiscoveredDevice or None if parsing fails
        """
        try:
            # Try to decode as JSON (newer firmware)
            try:
                response = json.loads(data.decode("utf-8"))
                return self._parse_json_response(response, ip_address)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            # Try to decode as plain text (older firmware)
            try:
                response_str = data.decode("utf-8")
                return self._parse_text_response(response_str, ip_address)
            except UnicodeDecodeError:
                pass

            logger.debug(f"Could not parse Bamboo response from {ip_address}")
            return None

        except Exception as e:
            logger.warning(f"Failed to parse Bamboo response: {e}")
            return None

    def _parse_json_response(
        self, response: dict, ip_address: str
    ) -> DiscoveredDevice:
        """
        Parse JSON-formatted Bamboo response.

        Args:
            response: Parsed JSON response
            ip_address: Source IP address

        Returns:
            DiscoveredDevice
        """
        # Extract device info
        model = response.get("model", "Unknown Bamboo Model")
        serial_number = response.get("serial", response.get("sn"))
        firmware_version = response.get("firmware", response.get("fw"))
        hostname = response.get("hostname", f"bamboo-{serial_number}")

        # Build capabilities
        capabilities = {
            "print_volume": response.get("print_volume"),
            "multi_material": response.get("multi_material", False),
            "ams_installed": response.get("ams", False),
        }

        # Remove None values
        capabilities = {k: v for k, v in capabilities.items() if v is not None}

        # Build services
        services = [
            DiscoveredServiceInfo(
                protocol="mqtt",
                port=1883,
                name="Bamboo Labs MQTT"
            )
        ]

        # Create device
        device = self._create_device(
            ip_address=ip_address,
            hostname=hostname,
            device_type=DeviceType.PRINTER_3D,
            manufacturer="Bamboo Labs",
            model=model,
            serial_number=serial_number,
            firmware_version=firmware_version,
            confidence_score=0.95,
            services=services,
            capabilities=capabilities
        )

        return device

    def _parse_text_response(
        self, response_str: str, ip_address: str
    ) -> DiscoveredDevice:
        """
        Parse plain text Bamboo response.

        Args:
            response_str: Response string
            ip_address: Source IP address

        Returns:
            DiscoveredDevice
        """
        # Simple key-value parsing
        lines = response_str.strip().split("\n")
        data = {}

        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()

        # Extract fields
        model = data.get("model", "Unknown Bamboo Model")
        serial_number = data.get("serial", data.get("sn"))
        firmware_version = data.get("firmware", data.get("fw"))
        hostname = data.get("hostname", f"bamboo-{serial_number}")

        # Build services
        services = [
            DiscoveredServiceInfo(
                protocol="mqtt",
                port=1883,
                name="Bamboo Labs MQTT"
            )
        ]

        # Create device
        device = self._create_device(
            ip_address=ip_address,
            hostname=hostname,
            device_type=DeviceType.PRINTER_3D,
            manufacturer="Bamboo Labs",
            model=model,
            serial_number=serial_number,
            firmware_version=firmware_version,
            confidence_score=0.90,
            services=services,
            capabilities={}
        )

        return device
