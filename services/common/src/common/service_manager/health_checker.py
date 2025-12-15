"""Health Checker for KITTY ServiceManager.

Provides async health checking for services using HTTP and TCP checks.
"""

import asyncio
import logging
import socket
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from .registry import ServiceRegistry, get_registry
from .types import HealthCheckType, HealthStatus, ServiceDefinition

logger = logging.getLogger(__name__)


class HealthChecker:
    """Async health checker for KITTY services.

    Supports HTTP GET, HTTP JSON, and TCP connect health checks.
    Uses httpx for async HTTP requests with connection pooling.
    """

    def __init__(
        self,
        registry: Optional[ServiceRegistry] = None,
        http_timeout: float = 5.0,
    ):
        """Initialize the health checker.

        Args:
            registry: ServiceRegistry to get service definitions from.
            http_timeout: Default timeout for HTTP requests in seconds.
        """
        self._registry = registry or get_registry()
        self._http_timeout = http_timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._last_health: Dict[str, HealthStatus] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._http_timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_health(self, service: ServiceDefinition) -> HealthStatus:
        """Check health of a single service.

        Args:
            service: The service definition to check.

        Returns:
            HealthStatus with check results.
        """
        start_time = datetime.now(timezone.utc)

        try:
            if service.health_check_type == HealthCheckType.HTTP_GET:
                return await self._check_http(service, start_time, parse_json=False)
            elif service.health_check_type == HealthCheckType.HTTP_JSON:
                return await self._check_http(service, start_time, parse_json=True)
            elif service.health_check_type == HealthCheckType.TCP_CONNECT:
                return await self._check_tcp(service, start_time)
            else:
                return HealthStatus(
                    service_name=service.name,
                    is_healthy=False,
                    checked_at=start_time,
                    error=f"Unknown health check type: {service.health_check_type}",
                )
        except Exception as e:
            logger.warning(f"Health check failed for {service.name}: {e}")
            return HealthStatus(
                service_name=service.name,
                is_healthy=False,
                checked_at=start_time,
                error=str(e),
            )

    async def _check_http(
        self,
        service: ServiceDefinition,
        start_time: datetime,
        parse_json: bool = False,
    ) -> HealthStatus:
        """Perform HTTP health check."""
        client = await self._get_client()
        timeout = service.health_timeout_seconds or self._http_timeout

        try:
            response = await client.get(
                service.health_url,
                timeout=timeout,
            )
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Check status code
            is_healthy = response.status_code == 200
            details = None

            # Parse JSON if requested
            if parse_json and is_healthy:
                try:
                    data = response.json()
                    details = data
                    # Check for explicit status field
                    if isinstance(data, dict) and "status" in data:
                        is_healthy = data["status"] in ("ok", "healthy", True)
                except Exception:
                    pass  # JSON parsing optional

            status = HealthStatus(
                service_name=service.name,
                is_healthy=is_healthy,
                checked_at=start_time,
                latency_ms=latency_ms,
                status_code=response.status_code,
                details=details,
            )

            # Log state changes
            self._log_state_change(service.name, status)
            self._last_health[service.name] = status

            return status

        except httpx.ConnectError as e:
            return HealthStatus(
                service_name=service.name,
                is_healthy=False,
                checked_at=start_time,
                error=f"Connection refused: {service.health_url}",
            )
        except httpx.TimeoutException:
            return HealthStatus(
                service_name=service.name,
                is_healthy=False,
                checked_at=start_time,
                error=f"Timeout after {timeout}s",
            )

    async def _check_tcp(
        self,
        service: ServiceDefinition,
        start_time: datetime,
    ) -> HealthStatus:
        """Perform TCP connect health check."""
        timeout = service.health_timeout_seconds or self._http_timeout

        def _tcp_connect() -> bool:
            """Blocking TCP connect check."""
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((service.host, service.port))
                sock.close()
                return result == 0
            except Exception:
                return False

        # Run blocking socket check in executor
        loop = asyncio.get_event_loop()
        is_healthy = await loop.run_in_executor(None, _tcp_connect)
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        status = HealthStatus(
            service_name=service.name,
            is_healthy=is_healthy,
            checked_at=start_time,
            latency_ms=latency_ms,
            error=None if is_healthy else f"Cannot connect to {service.host}:{service.port}",
        )

        self._log_state_change(service.name, status)
        self._last_health[service.name] = status

        return status

    def _log_state_change(self, service_name: str, new_status: HealthStatus) -> None:
        """Log health state changes."""
        old_status = self._last_health.get(service_name)
        if old_status is None:
            # First check
            state = "healthy" if new_status.is_healthy else "unhealthy"
            logger.info(f"Service {service_name}: initial check - {state}")
        elif old_status.is_healthy != new_status.is_healthy:
            # State changed
            if new_status.is_healthy:
                logger.info(f"Service {service_name}: recovered (now healthy)")
            else:
                logger.warning(
                    f"Service {service_name}: became unhealthy - {new_status.error}"
                )

    async def check_by_name(self, service_name: str) -> Optional[HealthStatus]:
        """Check health of a service by name.

        Args:
            service_name: Name of the service to check.

        Returns:
            HealthStatus or None if service not found.
        """
        service = self._registry.get(service_name)
        if service is None:
            logger.warning(f"Unknown service: {service_name}")
            return None
        return await self.check_health(service)

    async def check_all(self) -> Dict[str, HealthStatus]:
        """Check health of all services concurrently.

        Returns:
            Dict mapping service names to their health status.
        """
        services = self._registry.get_all()

        # Run all checks concurrently
        results = await asyncio.gather(
            *[self.check_health(svc) for svc in services.values()],
            return_exceptions=True,
        )

        # Build result dict
        health_map: Dict[str, HealthStatus] = {}
        for service, result in zip(services.values(), results):
            if isinstance(result, HealthStatus):
                health_map[service.name] = result
            else:
                # Exception occurred
                health_map[service.name] = HealthStatus(
                    service_name=service.name,
                    is_healthy=False,
                    error=str(result),
                )

        return health_map

    async def check_multiple(
        self, service_names: List[str]
    ) -> Dict[str, HealthStatus]:
        """Check health of specific services concurrently.

        Args:
            service_names: List of service names to check.

        Returns:
            Dict mapping service names to their health status.
        """
        services = [
            self._registry.get(name)
            for name in service_names
            if self._registry.get(name) is not None
        ]

        results = await asyncio.gather(
            *[self.check_health(svc) for svc in services],
            return_exceptions=True,
        )

        health_map: Dict[str, HealthStatus] = {}
        for service, result in zip(services, results):
            if isinstance(result, HealthStatus):
                health_map[service.name] = result
            else:
                health_map[service.name] = HealthStatus(
                    service_name=service.name,
                    is_healthy=False,
                    error=str(result),
                )

        return health_map

    def get_last_health(self, service_name: str) -> Optional[HealthStatus]:
        """Get the last known health status for a service.

        Args:
            service_name: Name of the service.

        Returns:
            Last HealthStatus or None if never checked.
        """
        return self._last_health.get(service_name)

    def get_all_last_health(self) -> Dict[str, HealthStatus]:
        """Get all last known health statuses."""
        return self._last_health.copy()
