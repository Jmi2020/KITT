"""
ICMP ping sweep scanner.

Discovers devices by sending ICMP echo requests (ping) across configured
subnets. This catches "quiet" devices that don't broadcast services via
mDNS/SSDP and is especially useful on macOS/Docker Desktop where multicast
support is limited.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import subprocess
from typing import List, Optional

from icmplib import multiping

from .base import BaseScanner, DiscoveryMethod, DeviceType, ScanResult

logger = logging.getLogger(__name__)


class PingScanner(BaseScanner):
    """
    ICMP ping sweep scanner (network_scan).

    Pings all hosts in the configured subnets to discover responsive devices.
    """

    def __init__(
        self,
        subnets: List[str],
        timeout_seconds: int = 5,
        ping_count: int = 1,
        ping_interval: float = 0.01,
        ping_timeout: float = 1.0,
        privileged: bool = True,
    ) -> None:
        """
        Args:
            subnets: List of CIDR blocks (e.g., ["192.168.1.0/24"])
            timeout_seconds: Overall timeout for the sweep
            ping_count: Number of pings per host
            ping_interval: Delay between pings (seconds)
            ping_timeout: Timeout per ping (seconds)
            privileged: Use raw sockets (requires NET_RAW capability)
        """
        super().__init__(timeout_seconds)
        self.subnets = subnets
        self.ping_count = ping_count
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.privileged = privileged

    @property
    def name(self) -> str:
        return "ICMP Ping Sweep"

    @property
    def discovery_method(self) -> DiscoveryMethod:
        return DiscoveryMethod.NETWORK_SCAN

    def _expand_hosts(self) -> List[str]:
        """Expand CIDR strings into individual host IPs."""
        hosts: List[str] = []
        for cidr in self.subnets:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                hosts.extend(str(host) for host in network.hosts())
                logger.debug("Expanded %s to %d hosts", cidr, network.num_addresses - 2)
            except ValueError as exc:
                logger.warning("Invalid CIDR %s: %s", cidr, exc)
        logger.info("Ping sweep will scan %d hosts across %d subnets", len(hosts), len(self.subnets))
        return hosts

    async def scan(self) -> ScanResult:
        """Run the ping sweep."""
        result = ScanResult(scanner_name=self.name)

        try:
            targets = self._expand_hosts()
            if not targets:
                logger.warning("No hosts to scan (empty subnet list)")
                result.complete(success=True)
                return result

            logger.info("Starting ping sweep of %d hosts", len(targets))
            loop = asyncio.get_event_loop()
            alive_hosts = await loop.run_in_executor(None, self._run_multiping, targets)

            for host in alive_hosts:
                if not host.is_alive:
                    continue
                mac = self._lookup_mac(host.address)
                capabilities = {
                    "latency_ms": round(host.avg_rtt, 2) if host.avg_rtt is not None else None,
                    "packet_loss": host.packet_loss,
                    "jitter_ms": round(host.jitter, 2) if host.jitter else None,
                    "mac_address": mac,
                }
                confidence = 0.3
                if mac:
                    confidence = 0.6  # bump when MAC is known for OUI/vendor tagging
                device = self._create_device(
                    ip_address=host.address,
                    device_type=DeviceType.UNKNOWN,
                    mac_address=mac,
                    confidence_score=confidence,
                    capabilities=capabilities,
                )
                result.add_device(device)

            logger.info(
                "Ping sweep complete: %d alive hosts (scanned %d IPs)",
                len(result.devices),
                len(targets),
            )
            result.complete(success=True)

        except Exception as exc:  # noqa: BLE001
            error_msg = f"Ping sweep failed: {exc}"
            logger.error(error_msg, exc_info=True)
            result.add_error(error_msg)
            result.complete(success=False)

        return result

    def _run_multiping(self, targets: List[str]):
        """Execute icmplib multiping synchronously."""
        try:
            return multiping(
                addresses=targets,
                count=self.ping_count,
                interval=self.ping_interval,
                timeout=self.ping_timeout,
                privileged=self.privileged,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("multiping execution failed: %s", exc, exc_info=True)
            return []

    @staticmethod
    def _lookup_mac(ip: str) -> Optional[str]:
        """
        Best-effort ARP lookup using `ip neigh show <ip>`.

        Works inside the Docker network; returns None on failure.
        """
        # Linux style: ip neigh
        try:
            out = subprocess.check_output(
                ["ip", "neigh", "show", ip],
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                text=True,
            )
            for line in out.splitlines():
                parts = line.split()
                if "lladdr" in parts:
                    idx = parts.index("lladdr")
                    if idx + 1 < len(parts):
                        mac = parts[idx + 1].strip()
                        if mac and mac.lower() != "failed":
                            return mac
        except Exception:
            pass

        # macOS/BSD style: arp -n <ip>
        try:
            out = subprocess.check_output(
                ["arp", "-n", ip],
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                text=True,
            )
            for line in out.splitlines():
                parts = line.replace("(", " ").replace(")", " ").split()
                for token in parts:
                    if token.count(":") == 5:  # rudimentary MAC pattern
                        return token.strip()
        except Exception:
            pass

        return None
