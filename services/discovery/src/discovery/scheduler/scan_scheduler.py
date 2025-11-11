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
from ..scanners.snapmaker_scanner import SnapmakerScanner
from ..scanners.ssdp_scanner import SSDPScanner

logger = logging.getLogger(__name__)


class ScanScheduler:
    """
    Manages periodic background discovery scans.

    Runs fast scans (mDNS, SSDP, UDP) at regular intervals to:
    - Update IP addresses for DHCP-assigned devices
    - Detect new devices coming online
    - Mark devices as offline if unreachable
    """

    def __init__(
        self,
        device_store: DeviceStore,
        interval_minutes: int = 15,
        enabled_scanners: Optional[List[str]] = None
    ):
        """
        Initialize scan scheduler.

        Args:
            device_store: Device registry storage
            interval_minutes: Scan interval in minutes
            enabled_scanners: List of enabled scanner names (default: all fast scanners)
        """
        self.device_store = device_store
        self.interval_minutes = interval_minutes
        self.enabled_scanners = enabled_scanners or [
            "mdns", "ssdp", "bamboo_udp", "snapmaker_udp"
        ]

        self.scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self) -> None:
        """Start the periodic scan scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        logger.info(
            f"Starting periodic discovery scans "
            f"(interval={self.interval_minutes}min, "
            f"scanners={self.enabled_scanners})"
        )

        # Schedule periodic scans
        self.scheduler.add_job(
            self._run_periodic_scan,
            trigger=IntervalTrigger(minutes=self.interval_minutes),
            id="periodic_discovery_scan",
            name="Periodic Discovery Scan",
            replace_existing=True
        )

        self.scheduler.start()
        self._running = True

        # Run initial scan immediately
        await self._run_periodic_scan()

    async def stop(self) -> None:
        """Stop the periodic scan scheduler."""
        if not self._running:
            return

        logger.info("Stopping periodic discovery scans")
        self.scheduler.shutdown()
        self._running = False

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
