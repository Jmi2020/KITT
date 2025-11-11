"""
Periodic scan scheduler.

Schedules background discovery scans at configurable intervals.
"""
import asyncio
import logging
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..registry.device_store import DeviceStore
from ..scanners.bamboo_scanner import BambooScanner
from ..scanners.mdns_scanner import MDNSScanner
from ..scanners.ping_scanner import PingScanner
from ..scanners.snapmaker_scanner import SnapmakerScanner
from ..scanners.ssdp_scanner import SSDPScanner

try:
    from common.config import Settings
except ImportError:
    Settings = None

logger = logging.getLogger(__name__)


class ScanScheduler:
    """
    Manages periodic background discovery scans.

    Runs fast scans (mDNS, SSDP, UDP) at regular intervals to:
    - Update IP addresses for DHCP-assigned devices
    - Detect new devices coming online
    - Mark devices as offline if unreachable

    Also schedules less frequent ping sweeps for comprehensive network coverage.
    """

    def __init__(
        self,
        device_store: DeviceStore,
        interval_minutes: int = 15,
        ping_sweep_interval_minutes: int = 60,
        enabled_scanners: Optional[List[str]] = None,
        subnets: Optional[List[str]] = None
    ):
        """
        Initialize scan scheduler.

        Args:
            device_store: Device registry storage
            interval_minutes: Fast scan interval in minutes (mDNS, SSDP, UDP)
            ping_sweep_interval_minutes: Ping sweep interval in minutes
            enabled_scanners: List of enabled scanner names (default: all fast scanners)
            subnets: Network subnets for ping sweep (e.g., ["192.168.1.0/24"])
        """
        self.device_store = device_store
        self.interval_minutes = interval_minutes
        self.ping_sweep_interval_minutes = ping_sweep_interval_minutes
        self.enabled_scanners = enabled_scanners or [
            "mdns", "ssdp", "bamboo_udp", "snapmaker_udp"
        ]
        self.subnets = subnets or ["192.168.1.0/24"]

        self.scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self) -> None:
        """Start the periodic scan scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        logger.info(
            f"Starting periodic discovery scans "
            f"(fast_interval={self.interval_minutes}min, "
            f"ping_interval={self.ping_sweep_interval_minutes}min, "
            f"scanners={self.enabled_scanners})"
        )

        # Schedule fast periodic scans (mDNS, SSDP, UDP)
        self.scheduler.add_job(
            self._run_periodic_scan,
            trigger=IntervalTrigger(minutes=self.interval_minutes),
            id="periodic_discovery_scan",
            name="Periodic Discovery Scan",
            replace_existing=True
        )

        # Schedule ping sweep (less frequent, more comprehensive)
        if "network_scan" in self.enabled_scanners:
            self.scheduler.add_job(
                self._run_ping_sweep,
                trigger=IntervalTrigger(minutes=self.ping_sweep_interval_minutes),
                id="periodic_ping_sweep",
                name="Periodic Ping Sweep",
                replace_existing=True
            )
            logger.info(f"Ping sweep enabled (interval={self.ping_sweep_interval_minutes}min)")

        self.scheduler.start()
        self._running = True

        # Run initial fast scan immediately
        await self._run_periodic_scan()

        # Run initial ping sweep if enabled
        if "network_scan" in self.enabled_scanners:
            await self._run_ping_sweep()

    async def stop(self) -> None:
        """Stop the periodic scan scheduler."""
        if not self._running:
            return

        logger.info("Stopping periodic discovery scans")
        self.scheduler.shutdown()
        self._running = False

    async def _run_ping_sweep(self) -> None:
        """
        Execute a periodic ping sweep.

        Runs ICMP ping across configured subnets to discover all responsive devices.
        """
        try:
            logger.info(f"Starting periodic ping sweep ({len(self.subnets)} subnets)")

            # Create scan record
            scan_record = await self.device_store.create_scan_record(
                methods=["network_scan"],
                triggered_by="scheduler"
            )

            # Initialize ping scanner
            ping_scanner = PingScanner(
                subnets=self.subnets,
                timeout_seconds=300,  # 5 minutes for large subnets
                ping_count=1,
                ping_interval=0.01,
                ping_timeout=1.0
            )

            # Run ping sweep
            result = await ping_scanner.scan()

            # Store discovered devices
            for device in result.devices:
                try:
                    await self.device_store.store_device(device, scan_id=scan_record.id)
                except Exception as e:
                    logger.error(f"Failed to store device: {e}")

            # Update scan record
            await self.device_store.update_scan_record(
                scan_id=scan_record.id,
                status="completed" if not result.errors else "completed_with_errors",
                devices_found=len(result.devices),
                errors=result.errors if result.errors else None
            )

            logger.info(
                f"Ping sweep completed: {len(result.devices)} devices found, "
                f"{len(result.errors)} errors"
            )

        except Exception as e:
            logger.error(f"Ping sweep failed: {e}", exc_info=True)

    async def _run_periodic_scan(self) -> None:
        """
        Execute a periodic discovery scan.

        Runs fast scanners and updates device registry.
        """
        try:
            logger.info("Starting periodic discovery scan")

            # Create scan record
            scan_record = await self.device_store.create_scan_record(
                methods=self.enabled_scanners,
                triggered_by="scheduler"
            )

            # Initialize scanners
            scanners = []
            if "mdns" in self.enabled_scanners:
                scanners.append(MDNSScanner(timeout_seconds=5))
            if "ssdp" in self.enabled_scanners:
                scanners.append(SSDPScanner(timeout_seconds=3))
            if "bamboo_udp" in self.enabled_scanners:
                scanners.append(BambooScanner(timeout_seconds=2))
            if "snapmaker_udp" in self.enabled_scanners:
                scanners.append(SnapmakerScanner(timeout_seconds=2))

            # Run all scanners concurrently
            scan_tasks = [scanner.scan() for scanner in scanners]
            results = await asyncio.gather(*scan_tasks, return_exceptions=True)

            # Collect devices and errors
            total_devices = 0
            all_errors = []

            for result in results:
                if isinstance(result, Exception):
                    all_errors.append(str(result))
                    logger.error(f"Scanner failed: {result}")
                else:
                    total_devices += len(result.devices)
                    all_errors.extend(result.errors)

                    # Store discovered devices
                    for device in result.devices:
                        try:
                            await self.device_store.store_device(
                                device, scan_id=scan_record.id
                            )
                        except Exception as e:
                            logger.error(f"Failed to store device: {e}")
                            all_errors.append(f"Store failed: {e}")

            # Update scan record
            await self.device_store.update_scan_record(
                scan_id=scan_record.id,
                status="completed" if not all_errors else "completed_with_errors",
                devices_found=total_devices,
                errors=all_errors if all_errors else None
            )

            logger.info(
                f"Periodic scan completed: {total_devices} devices found, "
                f"{len(all_errors)} errors"
            )

        except Exception as e:
            logger.error(f"Periodic scan failed: {e}", exc_info=True)

    async def trigger_manual_scan(
        self, methods: Optional[List[str]] = None, timeout_seconds: int = 30
    ) -> str:
        """
        Trigger a manual on-demand scan.

        Args:
            methods: Scanner methods to use (None = all enabled)
            timeout_seconds: Timeout for each scanner

        Returns:
            Scan ID (UUID)
        """
        methods = methods or self.enabled_scanners

        logger.info(f"Starting manual discovery scan (methods={methods})")

        # Create scan record
        scan_record = await self.device_store.create_scan_record(
            methods=methods,
            triggered_by="manual"
        )

        # Run scan in background task
        asyncio.create_task(
            self._run_manual_scan(scan_record.id, methods, timeout_seconds)
        )

        return str(scan_record.id)

    async def _run_manual_scan(
        self, scan_id: str, methods: List[str], timeout_seconds: int
    ) -> None:
        """
        Execute a manual discovery scan.

        Args:
            scan_id: Scan record ID
            methods: Scanner methods to use
            timeout_seconds: Timeout for each scanner
        """
        try:
            # Initialize scanners
            scanners = []
            if "mdns" in methods:
                scanners.append(MDNSScanner(timeout_seconds=timeout_seconds))
            if "ssdp" in methods:
                scanners.append(SSDPScanner(timeout_seconds=timeout_seconds))
            if "bamboo_udp" in methods:
                scanners.append(BambooScanner(timeout_seconds=min(5, timeout_seconds)))
            if "snapmaker_udp" in methods:
                scanners.append(SnapmakerScanner(timeout_seconds=min(5, timeout_seconds)))
            if "network_scan" in methods:
                scanners.append(PingScanner(
                    subnets=self.subnets,
                    timeout_seconds=timeout_seconds,
                    ping_count=1,
                    ping_interval=0.01,
                    ping_timeout=1.0
                ))

            # Run all scanners concurrently
            scan_tasks = [scanner.scan() for scanner in scanners]
            results = await asyncio.gather(*scan_tasks, return_exceptions=True)

            # Collect devices and errors
            total_devices = 0
            all_errors = []

            for result in results:
                if isinstance(result, Exception):
                    all_errors.append(str(result))
                    logger.error(f"Scanner failed: {result}")
                else:
                    total_devices += len(result.devices)
                    all_errors.extend(result.errors)

                    # Store discovered devices
                    for device in result.devices:
                        try:
                            await self.device_store.store_device(device, scan_id=scan_id)
                        except Exception as e:
                            logger.error(f"Failed to store device: {e}")
                            all_errors.append(f"Store failed: {e}")

            # Update scan record
            await self.device_store.update_scan_record(
                scan_id=scan_id,
                status="completed" if not all_errors else "completed_with_errors",
                devices_found=total_devices,
                errors=all_errors if all_errors else None
            )

            logger.info(
                f"Manual scan completed: {total_devices} devices found, "
                f"{len(all_errors)} errors"
            )

        except Exception as e:
            logger.error(f"Manual scan failed: {e}", exc_info=True)

            # Update scan record with failure
            await self.device_store.update_scan_record(
                scan_id=scan_id,
                status="failed",
                errors=[str(e)]
            )
