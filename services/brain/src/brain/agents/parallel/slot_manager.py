"""
Slot manager for async resource tracking across model endpoints.

Provides:
- Async slot acquisition with timeout and backoff
- Automatic fallback to secondary tiers
- Health checking and endpoint status
- Centralized slot tracking for the orchestrator
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import httpx

from .types import ModelTier
from .registry import ENDPOINTS, ModelEndpoint

# Optional import for process manager (only used if auto-restart is enabled)
try:
    from .process_manager import ProcessManager, get_process_manager
    PROCESS_MANAGER_AVAILABLE = True
except ImportError:
    PROCESS_MANAGER_AVAILABLE = False

logger = logging.getLogger("brain.parallel.slots")


class SlotManager:
    """
    Centralized slot management across all model endpoints.

    Handles:
    - Slot acquisition with exponential backoff
    - Automatic fallback to secondary tiers
    - Health checking before slot assignment
    - Status reporting for monitoring

    Usage:
        manager = SlotManager()

        # Acquire slot with fallback
        tier, acquired = await manager.acquire_slot(
            ModelTier.Q4_TOOLS,
            allow_fallback=True,
            fallback_tier=ModelTier.CODER
        )

        try:
            # Use the slot...
            pass
        finally:
            await manager.release_slot(tier)
    """

    def __init__(
        self,
        endpoints: Optional[Dict[ModelTier, ModelEndpoint]] = None,
        health_check_timeout: float = 5.0,
        auto_restart: bool = True,
    ):
        """
        Initialize slot manager.

        Args:
            endpoints: Custom endpoint registry (uses global ENDPOINTS if None)
            health_check_timeout: Timeout for health check requests
            auto_restart: Whether to auto-start stopped servers on slot acquisition
        """
        self._endpoints = endpoints or ENDPOINTS
        self._health_timeout = health_check_timeout
        self._http_client: Optional[httpx.AsyncClient] = None
        self._auto_restart = auto_restart and PROCESS_MANAGER_AVAILABLE
        # Track when each tier was last used (for idle shutdown)
        self._last_used: Dict[ModelTier, datetime] = {}
        self._last_used_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for health checks."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self._health_timeout)
        return self._http_client

    async def _ensure_server_running(
        self,
        tier: ModelTier,
        endpoint: ModelEndpoint,
        startup_wait: float = 30.0,
    ) -> bool:
        """
        Ensure a server is running, starting it if necessary.

        Args:
            tier: Model tier to start
            endpoint: Endpoint configuration
            startup_wait: Max seconds to wait for server startup

        Returns:
            True if server is running, False if startup failed
        """
        if not PROCESS_MANAGER_AVAILABLE:
            logger.warning("ProcessManager not available, cannot auto-restart")
            return False

        # Skip Ollama - it manages itself
        if tier == ModelTier.GPTOSS_REASON:
            return True

        logger.info(f"Auto-starting {tier.value} server...")
        process_manager = get_process_manager()
        pid = await process_manager.start_server(tier)

        if not pid:
            logger.error(f"Failed to start {tier.value} server")
            return False

        # Wait for server to become healthy
        wait_start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - wait_start < startup_wait:
            if await self.check_health(tier):
                endpoint._is_running = True
                await self.mark_tier_active(tier)  # Reset idle timer
                logger.info(f"Server {tier.value} is ready")
                return True
            await asyncio.sleep(1.0)

        logger.error(f"Server {tier.value} failed to become healthy")
        return False

    async def acquire_slot(
        self,
        tier: ModelTier,
        timeout: float = 30.0,
        allow_fallback: bool = True,
        fallback_tier: Optional[ModelTier] = None,
        max_retries: int = 10,
        base_delay: float = 0.5,
    ) -> Tuple[ModelTier, bool]:
        """
        Try to acquire a slot on the specified tier with optional fallback.

        Uses exponential backoff when slots are unavailable.

        Args:
            tier: Primary model tier to acquire slot on
            timeout: Maximum time to wait for slot
            allow_fallback: Whether to try fallback tier if primary is full
            fallback_tier: Specific fallback tier (optional)
            max_retries: Maximum acquisition attempts
            base_delay: Base delay for exponential backoff

        Returns:
            Tuple of (actual_tier_used, success_bool)

        Raises:
            asyncio.TimeoutError: If timeout exceeded without acquiring slot
        """
        endpoint = self._endpoints.get(tier)
        if not endpoint:
            logger.warning(f"Unknown tier {tier}, cannot acquire slot")
            return tier, False

        # Auto-restart stopped server if enabled
        if self._auto_restart and not endpoint._is_running:
            await self._ensure_server_running(tier, endpoint)

        # Try primary tier with backoff
        start_time = asyncio.get_event_loop().time()
        for attempt in range(max_retries):
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                break

            if await endpoint.acquire_slot():
                logger.debug(
                    f"Acquired slot on {tier.value} "
                    f"({endpoint.active_slots}/{endpoint.max_slots})"
                )
                return tier, True

            # Calculate backoff delay
            delay = min(base_delay * (2 ** attempt), timeout - elapsed)
            if delay <= 0:
                break

            logger.debug(
                f"Slot busy on {tier.value}, retry {attempt + 1}/{max_retries} "
                f"in {delay:.2f}s"
            )
            await asyncio.sleep(delay)

        # Try fallback tier if enabled
        if allow_fallback and fallback_tier:
            fallback_endpoint = self._endpoints.get(fallback_tier)
            if fallback_endpoint and await fallback_endpoint.acquire_slot():
                logger.info(
                    f"Primary tier {tier.value} full, using fallback {fallback_tier.value}"
                )
                return fallback_tier, True

        logger.warning(
            f"Could not acquire slot on {tier.value} after {max_retries} retries"
        )
        return tier, False

    async def release_slot(self, tier: ModelTier) -> None:
        """
        Release a slot back to the specified tier.

        Also records the release time for idle tracking.

        Args:
            tier: Model tier to release slot on
        """
        endpoint = self._endpoints.get(tier)
        if endpoint:
            await endpoint.release_slot()
            # Track when this tier was last used
            async with self._last_used_lock:
                self._last_used[tier] = datetime.now(timezone.utc)
            logger.debug(
                f"Released slot on {tier.value} "
                f"({endpoint.active_slots}/{endpoint.max_slots})"
            )
        else:
            logger.warning(f"Unknown tier {tier}, cannot release slot")

    async def check_health(self, tier: ModelTier) -> bool:
        """
        Check if an endpoint is healthy and responding.

        Args:
            tier: Model tier to check

        Returns:
            True if endpoint is healthy, False otherwise
        """
        endpoint = self._endpoints.get(tier)
        if not endpoint:
            return False

        try:
            client = await self._get_client()

            # Different health check paths for Ollama vs llama.cpp
            if "11434" in endpoint.base_url:
                # Ollama
                url = f"{endpoint.base_url}/api/tags"
            else:
                # llama.cpp
                url = f"{endpoint.base_url}/health"

            response = await client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for {tier.value}: {e}")
            return False

    async def check_all_health(self) -> Dict[str, bool]:
        """
        Check health of all endpoints concurrently.

        Returns:
            Dict mapping tier name to health status
        """
        results = await asyncio.gather(
            *[self.check_health(tier) for tier in self._endpoints.keys()],
            return_exceptions=True,
        )

        return {
            tier.value: result if isinstance(result, bool) else False
            for tier, result in zip(self._endpoints.keys(), results)
        }

    def get_status(self) -> Dict[str, Dict]:
        """
        Get current slot status for all endpoints.

        Returns:
            Dict mapping tier name to status dict with active/max/available
        """
        return {
            tier.value: endpoint.status()
            for tier, endpoint in self._endpoints.items()
        }

    def get_available_slots(self, tier: ModelTier) -> int:
        """
        Get number of available slots on a tier.

        Args:
            tier: Model tier to check

        Returns:
            Number of available slots, or 0 if tier unknown
        """
        endpoint = self._endpoints.get(tier)
        return endpoint.available_slots if endpoint else 0

    def total_capacity(self) -> int:
        """Get total slot capacity across all endpoints."""
        return sum(e.max_slots for e in self._endpoints.values())

    def total_active(self) -> int:
        """Get total active slots across all endpoints."""
        return sum(e.active_slots for e in self._endpoints.values())

    def total_available(self) -> int:
        """Get total available slots across all endpoints."""
        return sum(e.available_slots for e in self._endpoints.values())

    async def get_idle_seconds(self, tier: ModelTier) -> Optional[float]:
        """
        Get how many seconds a tier has been idle.

        Args:
            tier: Model tier to check

        Returns:
            Seconds since last use, or None if never used or currently active
        """
        endpoint = self._endpoints.get(tier)
        if not endpoint:
            return None

        # If there are active slots, it's not idle
        if endpoint.active_slots > 0:
            return None

        async with self._last_used_lock:
            last_used = self._last_used.get(tier)

        if last_used is None:
            return None

        now = datetime.now(timezone.utc)
        return (now - last_used).total_seconds()

    async def get_idle_tiers(self) -> Dict[ModelTier, float]:
        """
        Get all tiers that are currently idle with their idle duration.

        Returns:
            Dict mapping tier to idle seconds (only includes truly idle tiers)
        """
        result = {}
        for tier in self._endpoints:
            idle_seconds = await self.get_idle_seconds(tier)
            if idle_seconds is not None:
                result[tier] = idle_seconds
        return result

    async def is_tier_idle(self, tier: ModelTier, threshold_seconds: float) -> bool:
        """
        Check if a tier has been idle longer than the threshold.

        Args:
            tier: Model tier to check
            threshold_seconds: Idle time threshold

        Returns:
            True if idle longer than threshold, False otherwise
        """
        idle_seconds = await self.get_idle_seconds(tier)
        return idle_seconds is not None and idle_seconds >= threshold_seconds

    async def mark_tier_active(self, tier: ModelTier) -> None:
        """
        Mark a tier as recently active (clears idle timer).

        Called when a server is started to prevent immediate shutdown.
        """
        async with self._last_used_lock:
            self._last_used[tier] = datetime.now(timezone.utc)

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance for shared access
_slot_manager: Optional[SlotManager] = None


def get_slot_manager() -> SlotManager:
    """Get or create the global slot manager instance."""
    global _slot_manager
    if _slot_manager is None:
        _slot_manager = SlotManager()
    return _slot_manager


async def reset_slot_manager() -> None:
    """Reset the global slot manager (for testing)."""
    global _slot_manager
    if _slot_manager:
        await _slot_manager.close()
    _slot_manager = None
