"""
IdleReaper: Background task for shutting down idle llama.cpp servers.

Monitors endpoint usage and triggers shutdown when servers have been
idle longer than their configured idle_shutdown_seconds threshold.

This helps free VRAM on the Mac Studio M3 Ultra when models are not
in active use, while keeping the system ready to restart them on demand.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Dict, Optional

from .types import ModelTier
from .registry import ENDPOINTS, ModelEndpoint

if TYPE_CHECKING:
    from .slot_manager import SlotManager

logger = logging.getLogger("brain.parallel.idle_reaper")


class IdleReaper:
    """
    Background task that monitors and shuts down idle llama.cpp servers.

    Checks all endpoints periodically and shuts down those that have been
    idle longer than their configured threshold.

    Usage:
        reaper = IdleReaper(
            slot_manager=slot_manager,
            shutdown_callback=process_manager.stop_server,
        )
        await reaper.start(interval=60)

        # Later...
        await reaper.stop()
    """

    def __init__(
        self,
        slot_manager: "SlotManager",
        shutdown_callback: Optional[Callable[[ModelTier], asyncio.Future]] = None,
        endpoints: Optional[Dict[ModelTier, ModelEndpoint]] = None,
    ):
        """
        Initialize the idle reaper.

        Args:
            slot_manager: SlotManager instance for idle tracking
            shutdown_callback: Async callback to shut down a server (tier -> None)
            endpoints: Custom endpoint registry (uses global ENDPOINTS if None)
        """
        self._slot_manager = slot_manager
        self._shutdown_callback = shutdown_callback
        self._endpoints = endpoints or ENDPOINTS
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._check_interval = 60.0  # seconds

    async def check_and_shutdown_idle(self) -> Dict[ModelTier, bool]:
        """
        Check all endpoints and shut down those that are idle.

        Returns:
            Dict mapping tier to whether it was shut down
        """
        results: Dict[ModelTier, bool] = {}

        for tier, endpoint in self._endpoints.items():
            # Skip endpoints that don't have idle shutdown configured
            if endpoint.idle_shutdown_seconds <= 0:
                continue

            # Skip if endpoint is already marked as not running
            if not endpoint._is_running:
                continue

            # Check if this tier has been idle long enough
            is_idle = await self._slot_manager.is_tier_idle(
                tier, endpoint.idle_shutdown_seconds
            )

            if is_idle:
                idle_seconds = await self._slot_manager.get_idle_seconds(tier)
                logger.info(
                    f"Tier {tier.value} has been idle for {idle_seconds:.0f}s "
                    f"(threshold: {endpoint.idle_shutdown_seconds}s), shutting down"
                )

                if self._shutdown_callback:
                    try:
                        await self._shutdown_callback(tier)
                        endpoint._is_running = False
                        results[tier] = True
                        logger.info(f"Successfully shut down {tier.value}")
                    except Exception as e:
                        logger.error(f"Failed to shut down {tier.value}: {e}")
                        results[tier] = False
                else:
                    logger.warning(
                        f"No shutdown callback configured, cannot stop {tier.value}"
                    )
                    results[tier] = False
            else:
                results[tier] = False

        return results

    async def _run_loop(self) -> None:
        """Background loop that periodically checks for idle endpoints."""
        logger.info(
            f"IdleReaper started, checking every {self._check_interval}s"
        )

        while self._running:
            try:
                await self.check_and_shutdown_idle()
            except Exception as e:
                logger.error(f"Error in idle reaper loop: {e}")

            # Sleep until next check
            await asyncio.sleep(self._check_interval)

    async def start(self, interval: float = 60.0) -> None:
        """
        Start the background idle reaper task.

        Args:
            interval: Seconds between idle checks
        """
        if self._running:
            logger.warning("IdleReaper already running")
            return

        self._check_interval = interval
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"IdleReaper started with {interval}s interval")

    async def stop(self) -> None:
        """Stop the background idle reaper task."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("IdleReaper stopped")

    @property
    def is_running(self) -> bool:
        """Check if the reaper is currently running."""
        return self._running

    def get_status(self) -> Dict:
        """Get current reaper status for monitoring."""
        return {
            "running": self._running,
            "check_interval": self._check_interval,
            "endpoints_monitored": len([
                e for e in self._endpoints.values()
                if e.idle_shutdown_seconds > 0
            ]),
        }
