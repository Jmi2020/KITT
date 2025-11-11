"""
ICMP ping sweep scanner.

Discovers devices via ICMP echo requests (ping). Works well across all network
topologies and catches "quiet" devices that don't advertise via mDNS/SSDP.

Requires NET_RAW capability in Docker.
"""
import asyncio
import ipaddress
import logging
from datetime import datetime
from typing import List

from icmplib import multiping

from .base import BaseScanner, DiscoveredDevice, DiscoveryMethod, DeviceType, ScanResult

logger = logging.getLogger(__name__)


class PingScanner(BaseScanner):
    """
    ICMP ping sweep scanner.

    Pings all hosts in configured subnets to discover responsive devices.
    This is the most universal discovery method but doesn't provide device
    metadata without additional probing.
    """

    def __init__(
        self,
        subnets: List[str],
        timeout_seconds: int = 5,
        ping_count: int = 1,
        ping_interval: float = 0.01,  # 10ms between pings
        ping_timeout: float = 1.0,  # 1s timeout per ping
        privileged: bool = True  # Use raw sockets (requires NET_RAW)
    ):
        """
        Initialize ping scanner.

        Args:
            subnets: List of CIDR subnets to scan (e.g., ["192.168.1.0/24"])
            timeout_seconds: Overall scan timeout
            ping_count: Number of pings per host
            ping_interval: Interval between pings in seconds
            ping_timeout: Timeout for each ping
            privileged: Use raw ICMP sockets (requires CAP_NET_RAW)
        """
        super().__init__(DiscoveryMethod.NETWORK_SCAN, timeout_seconds)
        self.subnets = subnets
        self.ping_count = ping_count
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.privileged = privileged

    def _expand_hosts(self) -> List[str]:
        """
        Expand CIDR subnets to list of host IP addresses.

        Returns:
            List of IP addresses to scan
        """
        hosts = []
        for cidr in self.subnets:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                # Use .hosts() to exclude network and broadcast addresses
                hosts.extend([str(h) for h in network.hosts()])
                logger.debug(f"Expanded {cidr} to {network.num_addresses - 2} hosts")
            except ValueError as e:
                logger.warning(f"Invalid CIDR {cidr}: {e}")
                continue

        logger.info(f"Ping sweep will scan {len(hosts)} hosts across {len(self.subnets)} subnets")
        return hosts

    async def scan(self) -> ScanResult:
        """
        Perform ICMP ping sweep.

        Returns:
            Scan result with discovered devices
        """
        result = ScanResult(
            method=self.method,
            started_at=datetime.utcnow(),
            devices=[],
            errors=[]
        )

        try:
            # Expand subnets to host list
            targets = self._expand_hosts()

            if not targets:
                logger.warning("No hosts to scan (empty subnet list)")
                result.completed_at = datetime.utcnow()
                return result

            logger.info(f"Starting ping sweep of {len(targets)} hosts")

            # Run ping sweep in executor (blocking operation)
            loop = asyncio.get_event_loop()
            alive_hosts = await loop.run_in_executor(
                None,
                self._run_multiping,
                targets
            )

            # Convert to DiscoveredDevice objects
            for host in alive_hosts:
                if host.is_alive:
                    device = DiscoveredDevice(
                        discovered_at=datetime.utcnow(),
                        discovery_method=self.method,
                        ip_address=host.address,
                        mac_address=None,  # ICMP doesn't provide MAC
                        hostname=None,  # Reverse DNS lookup could be added
                        device_type=DeviceType.UNKNOWN,  # No device info from ping
                        manufacturer=None,
                        model=None,
                        serial_number=None,
                        firmware_version=None,
                        services=[],
                        capabilities={
                            "latency_ms": round(host.avg_rtt, 2),
                            "packet_loss": host.packet_loss,
                            "jitter_ms": round(host.jitter, 2) if host.jitter else None
                        },
                        confidence_score=0.3  # Low confidence (just ping, no device ID)
                    )
                    result.devices.append(device)

            logger.info(
                f"Ping sweep complete: {len(result.devices)} alive hosts "
                f"(scanned {len(targets)} IPs)"
            )

        except Exception as e:
            error_msg = f"Ping sweep failed: {e}"
            logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)

        result.completed_at = datetime.utcnow()
        return result

    def _run_multiping(self, targets: List[str]) -> List:
        """
        Run multiping in synchronous context (executor).

        Args:
            targets: List of IP addresses to ping

        Returns:
            List of Host objects from icmplib
        """
        try:
            # multiping returns Host objects with is_alive, avg_rtt, packet_loss, etc.
            return multiping(
                addresses=targets,
                count=self.ping_count,
                interval=self.ping_interval,
                timeout=self.ping_timeout,
                privileged=self.privileged
            )
        except Exception as e:
            logger.error(f"multiping execution failed: {e}", exc_info=True)
            return []
