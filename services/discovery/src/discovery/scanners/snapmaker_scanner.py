"""
Snapmaker UDP discovery scanner.

Discovers Snapmaker 3-in-1 machines (CNC/laser/3D) via UDP broadcast on port 20054.
Uses JSON-based discovery protocol.
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


SNAPMAKER_DISCOVERY_PORT = 20054
SNAPMAKER_DISCOVERY_MESSAGE = json.dumps({
    "type": "discover",
    "version": "1.0"
}).encode("utf-8")


class SnapmakerScanner(BaseScanner):
    """
    Snapmaker machine discovery via UDP broadcast.

    Sends JSON discovery message to port 20054 and listens for responses.
    """

    def __init__(self, timeout_seconds: int = 2):
        """
        Initialize Snapmaker scanner.

        Args:
            timeout_seconds: How long to wait for UDP responses
        """
        super().__init__(timeout_seconds)

    @property
    def name(self) -> str:
        return "Snapmaker UDP"

    @property
    def discovery_method(self) -> DiscoveryMethod:
        return DiscoveryMethod.SNAPMAKER_UDP

    async def scan(self) -> ScanResult:
        """
        Execute Snapmaker UDP discovery scan.

        Returns:
            ScanResult with discovered Snapmaker machines
        """
        result = ScanResult(scanner_name=self.name)

        try:
            logger.info(f"Starting Snapmaker UDP scan (timeout={self.timeout_seconds}s)")

            # Run UDP discovery
            devices = await self._discover_snapmaker_machines()

            for device in devices:
                result.add_device(device)

            result.complete(success=True)
            logger.info(f"Snapmaker scan completed: {len(result.devices)} devices found")

        except Exception as e:
            logger.error(f"Snapmaker scan failed: {e}", exc_info=True)
            result.add_error(str(e))
            result.complete(success=False)

        return result

    async def _discover_snapmaker_machines(self) -> List[DiscoveredDevice]:
        """
        Send UDP broadcast and collect Snapmaker responses.

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
            broadcast_addr = ("<broadcast>", SNAPMAKER_DISCOVERY_PORT)
            sock.sendto(SNAPMAKER_DISCOVERY_MESSAGE, broadcast_addr)

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
                    device = self._parse_snapmaker_response(data, ip_address)
                    if device:
                        devices.append(device)

                except socket.timeout:
                    break
                except Exception as e:
                    logger.debug(f"Error receiving Snapmaker response: {e}")

            sock.close()

        except Exception as e:
            logger.error(f"Snapmaker UDP discovery failed: {e}")

        return devices

    def _parse_snapmaker_response(
        self, data: bytes, ip_address: str
    ) -> Optional[DiscoveredDevice]:
        """
        Parse Snapmaker UDP response.

        Args:
            data: UDP response data (JSON)
            ip_address: Source IP address

        Returns:
            DiscoveredDevice or None if parsing fails
        """
        try:
            # Decode JSON response
            response = json.loads(data.decode("utf-8"))

            # Validate response type
            if response.get("type") != "discover_response":
                return None

            # Extract device info
            model = response.get("model", "Unknown Snapmaker Model")
            serial_number = response.get("serial", response.get("sn"))
            firmware_version = response.get("version", response.get("firmware"))
            hostname = response.get("name", f"snapmaker-{serial_number}")

            # Determine device type (most Snapmakers are CNC-capable)
            # Snapmaker 2.0 and Artisan support 3D printing, CNC, and laser
            device_type = DeviceType.PRINTER_CNC

            # Extract capabilities
            modules = response.get("modules", [])
            capabilities = {
                "work_volume": response.get("work_volume"),
                "modules": modules,
                "supports_3d_print": "3dp" in modules or "print" in model.lower(),
                "supports_cnc": "cnc" in modules or True,  # Most Snapmakers support CNC
                "supports_laser": "laser" in modules or True,  # Most Snapmakers support laser
            }

            # Remove None values
            capabilities = {k: v for k, v in capabilities.items() if v is not None}

            # Build services
            services = [
                DiscoveredServiceInfo(
                    protocol="http",
                    port=8080,
                    name="Snapmaker HTTP API"
                )
            ]

            # Create device
            device = self._create_device(
                ip_address=ip_address,
                hostname=hostname,
                device_type=device_type,
                manufacturer="Snapmaker",
                model=model,
                serial_number=serial_number,
                firmware_version=firmware_version,
                confidence_score=0.95,
                services=services,
                capabilities=capabilities
            )

            return device

        except json.JSONDecodeError:
            logger.debug(f"Invalid JSON response from {ip_address}")
            return None
        except Exception as e:
            logger.warning(f"Failed to parse Snapmaker response: {e}")
            return None
