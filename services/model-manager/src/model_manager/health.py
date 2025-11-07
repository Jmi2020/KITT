# noqa: D401
"""Health checking for llama.cpp server."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from .models import ServerConfig, ServerStatus

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    status: ServerStatus
    latency_ms: float
    slots_idle: Optional[int] = None
    slots_processing: Optional[int] = None
    model_loaded: bool = False
    error: Optional[str] = None


class HealthCheckError(Exception):
    """Exception raised when health check fails."""

    pass


class HealthChecker:
    """Health checker for llama.cpp server with retry logic."""

    def __init__(
        self,
        endpoint: str,
        timeout: int = 5,
        max_retries: int = 120,
        retry_delay: float = 1.0,
        backoff_factor: float = 1.1,
        max_delay: float = 10.0,
    ) -> None:
        """Initialize health checker.

        Args:
            endpoint: Server endpoint (e.g., http://localhost:8080)
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            backoff_factor: Exponential backoff multiplier
            max_delay: Maximum delay between retries
        """
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

        self._client = httpx.AsyncClient(timeout=timeout)

    async def check(self) -> HealthCheckResult:
        """Perform single health check.

        Returns:
            HealthCheckResult with server status and metrics

        Raises:
            HealthCheckError: If health check fails
        """
        start_time = time.time()

        try:
            response = await self._client.get(f"{self.endpoint}/health")
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                return HealthCheckResult(
                    status=ServerStatus.READY,
                    latency_ms=latency_ms,
                    slots_idle=data.get("slots_idle"),
                    slots_processing=data.get("slots_processing"),
                    model_loaded=True,
                )
            elif response.status_code == 503:
                # Server is up but model not loaded yet
                data = response.json()
                return HealthCheckResult(
                    status=ServerStatus.LOADING,
                    latency_ms=latency_ms,
                    error=data.get("error", "Model loading"),
                    model_loaded=False,
                )
            else:
                return HealthCheckResult(
                    status=ServerStatus.FAILED,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                )

        except httpx.ConnectError:
            latency_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                status=ServerStatus.STARTING,
                latency_ms=latency_ms,
                error="Connection refused",
            )
        except httpx.TimeoutException:
            latency_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                status=ServerStatus.LOADING,
                latency_ms=latency_ms,
                error="Request timeout",
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                status=ServerStatus.FAILED,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def wait_for_ready(
        self,
        on_progress: Optional[Callable[[HealthCheckResult, int, int], None]] = None,
    ) -> HealthCheckResult:
        """Wait for server to become ready with exponential backoff.

        Args:
            on_progress: Optional callback for progress updates
                         (result, attempt, max_attempts)

        Returns:
            HealthCheckResult when server is ready

        Raises:
            HealthCheckError: If server doesn't become ready within max_retries
        """
        delay = self.retry_delay
        last_result = None

        for attempt in range(1, self.max_retries + 1):
            result = await self.check()
            last_result = result

            # Call progress callback
            if on_progress:
                on_progress(result, attempt, self.max_retries)

            # Check if ready
            if result.status == ServerStatus.READY:
                logger.info(
                    f"Server ready after {attempt} attempts "
                    f"({result.latency_ms:.1f}ms latency)"
                )
                return result

            # Log status
            logger.debug(
                f"Attempt {attempt}/{self.max_retries}: "
                f"status={result.status.value}, "
                f"latency={result.latency_ms:.1f}ms, "
                f"error={result.error}"
            )

            # Wait before retrying
            if attempt < self.max_retries:
                await asyncio.sleep(delay)
                # Exponential backoff
                delay = min(delay * self.backoff_factor, self.max_delay)

        # Failed to become ready
        error_msg = (
            f"Server failed to become ready after {self.max_retries} attempts. "
            f"Last status: {last_result.status.value if last_result else 'unknown'}"
        )
        if last_result and last_result.error:
            error_msg += f" ({last_result.error})"

        raise HealthCheckError(error_msg)

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> HealthChecker:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()


def sync_check_health(endpoint: str, timeout: int = 5) -> HealthCheckResult:
    """Synchronous health check helper.

    Args:
        endpoint: Server endpoint
        timeout: Request timeout

    Returns:
        HealthCheckResult
    """

    async def _check() -> HealthCheckResult:
        async with HealthChecker(endpoint, timeout=timeout) as checker:
            return await checker.check()

    return asyncio.run(_check())


def sync_wait_for_ready(
    endpoint: str,
    max_retries: int = 120,
    on_progress: Optional[Callable[[HealthCheckResult, int, int], None]] = None,
) -> HealthCheckResult:
    """Synchronous wait for ready helper.

    Args:
        endpoint: Server endpoint
        max_retries: Maximum retry attempts
        on_progress: Optional progress callback

    Returns:
        HealthCheckResult when ready

    Raises:
        HealthCheckError: If server doesn't become ready
    """

    async def _wait() -> HealthCheckResult:
        async with HealthChecker(endpoint, max_retries=max_retries) as checker:
            return await checker.wait_for_ready(on_progress=on_progress)

    return asyncio.run(_wait())


class HealthMonitor:
    """Continuous health monitoring with auto-restart support."""

    def __init__(
        self,
        endpoint: str,
        check_interval: float = 30.0,
        failure_threshold: int = 3,
    ) -> None:
        """Initialize health monitor.

        Args:
            endpoint: Server endpoint
            check_interval: Seconds between health checks
            failure_threshold: Consecutive failures before marking unhealthy
        """
        self.endpoint = endpoint
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold

        self._checker = HealthChecker(endpoint)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._consecutive_failures = 0
        self._on_unhealthy: Optional[Callable[[], None]] = None

    def set_unhealthy_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to invoke when server becomes unhealthy.

        Args:
            callback: Function to call when unhealthy
        """
        self._on_unhealthy = callback

    async def start(self) -> None:
        """Start monitoring loop."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor started")

    async def stop(self) -> None:
        """Stop monitoring loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._checker.close()
        logger.info("Health monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                result = await self._checker.check()

                if result.status == ServerStatus.READY:
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                    logger.warning(
                        f"Health check failed ({self._consecutive_failures}/"
                        f"{self.failure_threshold}): {result.error}"
                    )

                    if self._consecutive_failures >= self.failure_threshold:
                        logger.error("Server unhealthy, invoking callback")
                        if self._on_unhealthy:
                            self._on_unhealthy()
                        # Reset counter after callback
                        self._consecutive_failures = 0

            except Exception as e:
                logger.error(f"Monitor error: {e}")

            # Wait for next check
            await asyncio.sleep(self.check_interval)


__all__ = [
    "HealthChecker",
    "HealthCheckResult",
    "HealthCheckError",
    "HealthMonitor",
    "sync_check_health",
    "sync_wait_for_ready",
]
