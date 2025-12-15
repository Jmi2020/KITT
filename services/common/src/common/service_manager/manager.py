"""ServiceManager for KITTY.

Main orchestrator that provides on-demand service activation,
health monitoring, and status reporting.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .docker_starter import DockerStarter
from .health_checker import HealthChecker
from .native_starter import NativeStarter
from .registry import ServiceRegistry, get_registry
from .types import HealthStatus, ServiceDefinition, ServiceStatus, ServiceType

logger = logging.getLogger(__name__)


class ServiceManager:
    """Unified service management for KITTY.

    Provides:
    - Health checking for all services
    - On-demand service activation (auto-start when needed)
    - Status reporting via API
    - Integration with Brain service lifespan

    Unlike IdleReaper (which manages LLM idle shutdown), ServiceManager
    handles all other services and focuses on on-demand activation rather
    than idle management.
    """

    def __init__(
        self,
        registry: Optional[ServiceRegistry] = None,
        health_checker: Optional[HealthChecker] = None,
        native_starter: Optional[NativeStarter] = None,
        docker_starter: Optional[DockerStarter] = None,
    ):
        """Initialize the ServiceManager.

        Args:
            registry: ServiceRegistry with service definitions.
            health_checker: HealthChecker for health monitoring.
            native_starter: NativeStarter for native processes.
            docker_starter: DockerStarter for Docker services.
        """
        self._registry = registry or get_registry()
        self._health_checker = health_checker or HealthChecker(self._registry)
        self._native_starter = native_starter or NativeStarter(self._health_checker)
        self._docker_starter = docker_starter or DockerStarter(self._health_checker)

        # Track service start times
        self._last_started: Dict[str, datetime] = {}

        # Lock for ensuring only one start at a time per service
        self._start_locks: Dict[str, asyncio.Lock] = {}

        logger.info(
            f"ServiceManager initialized with {self._registry.count} services "
            f"({len(self._registry.get_auto_startable())} auto-startable)"
        )

    def _get_lock(self, service_name: str) -> asyncio.Lock:
        """Get or create a lock for a service."""
        if service_name not in self._start_locks:
            self._start_locks[service_name] = asyncio.Lock()
        return self._start_locks[service_name]

    async def check_health(self, service_name: str) -> Optional[HealthStatus]:
        """Check health of a single service.

        Args:
            service_name: Name of the service to check.

        Returns:
            HealthStatus or None if service not found.
        """
        return await self._health_checker.check_by_name(service_name)

    async def check_all_health(self) -> Dict[str, HealthStatus]:
        """Check health of all registered services.

        Returns:
            Dict mapping service names to their health status.
        """
        return await self._health_checker.check_all()

    async def ensure_running(self, service_name: str) -> bool:
        """Ensure a service is running, starting it if necessary.

        This is the main on-demand activation method. It:
        1. Checks if the service is already healthy
        2. If not, attempts to start it (if auto-start enabled)
        3. Waits for health check to pass

        Args:
            service_name: Name of the service to ensure is running.

        Returns:
            True if service is now running and healthy, False otherwise.
        """
        service = self._registry.get(service_name)
        if service is None:
            logger.warning(f"Unknown service: {service_name}")
            return False

        # Quick check - is it already healthy?
        health = await self._health_checker.check_health(service)
        if health.is_healthy:
            return True

        # Not healthy - can we auto-start it?
        if not service.auto_start_enabled:
            logger.info(
                f"Service {service_name} is not healthy and auto-start is disabled"
            )
            return False

        # Acquire lock to prevent concurrent starts
        lock = self._get_lock(service_name)
        async with lock:
            # Double-check after acquiring lock
            health = await self._health_checker.check_health(service)
            if health.is_healthy:
                return True

            logger.info(f"Auto-starting service: {service_name}")
            success = await self.start_service(service_name)

            if success:
                self._last_started[service_name] = datetime.now(timezone.utc)

            return success

    async def start_service(self, service_name: str) -> bool:
        """Start a service.

        Args:
            service_name: Name of the service to start.

        Returns:
            True if started successfully, False otherwise.
        """
        service = self._registry.get(service_name)
        if service is None:
            logger.warning(f"Unknown service: {service_name}")
            return False

        # Check dependencies first
        for dep_name in service.depends_on:
            dep_healthy = await self.ensure_running(dep_name)
            if not dep_healthy:
                logger.error(
                    f"Cannot start {service_name}: dependency {dep_name} not available"
                )
                return False

        # Start based on service type
        if service.service_type == ServiceType.NATIVE_PROCESS:
            return await self._native_starter.start_service(service)
        elif service.service_type in (ServiceType.DOCKER_SERVICE, ServiceType.DOCKER_INFRA):
            return await self._docker_starter.start_service(service)
        else:
            logger.error(f"Unknown service type for {service_name}")
            return False

    async def stop_service(self, service_name: str) -> bool:
        """Stop a service.

        Args:
            service_name: Name of the service to stop.

        Returns:
            True if stopped successfully, False otherwise.
        """
        service = self._registry.get(service_name)
        if service is None:
            logger.warning(f"Unknown service: {service_name}")
            return False

        if service.service_type == ServiceType.NATIVE_PROCESS:
            return await self._native_starter.stop_service(service)
        elif service.service_type in (ServiceType.DOCKER_SERVICE, ServiceType.DOCKER_INFRA):
            return await self._docker_starter.stop_service(service)
        else:
            logger.error(f"Unknown service type for {service_name}")
            return False

    async def restart_service(self, service_name: str) -> bool:
        """Restart a service.

        Args:
            service_name: Name of the service to restart.

        Returns:
            True if restarted successfully, False otherwise.
        """
        service = self._registry.get(service_name)
        if service is None:
            logger.warning(f"Unknown service: {service_name}")
            return False

        if service.service_type == ServiceType.NATIVE_PROCESS:
            await self._native_starter.stop_service(service)
            return await self._native_starter.start_service(service)
        elif service.service_type in (ServiceType.DOCKER_SERVICE, ServiceType.DOCKER_INFRA):
            return await self._docker_starter.restart_service(service)
        else:
            return False

    async def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """Get detailed status of a service.

        Args:
            service_name: Name of the service.

        Returns:
            ServiceStatus or None if service not found.
        """
        service = self._registry.get(service_name)
        if service is None:
            return None

        health = await self._health_checker.check_health(service)

        # Get runtime info based on service type
        pid = None
        container_id = None
        is_running = health.is_healthy

        if service.service_type == ServiceType.NATIVE_PROCESS:
            pid = self._native_starter.get_pid(service)
            is_running = pid is not None
        elif service.service_type in (ServiceType.DOCKER_SERVICE, ServiceType.DOCKER_INFRA):
            container_id = await self._docker_starter.get_container_id(service)
            is_running = await self._docker_starter.is_running(service)

        # Calculate uptime if we know when it started
        uptime_seconds = None
        last_started = self._last_started.get(service_name)
        if last_started and is_running:
            uptime_seconds = (datetime.now(timezone.utc) - last_started).total_seconds()

        return ServiceStatus(
            service=service,
            health=health,
            is_running=is_running,
            pid=pid,
            container_id=container_id,
            uptime_seconds=uptime_seconds,
            last_started_at=last_started,
        )

    async def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all services.

        Returns:
            Dict mapping service names to their status dicts.
        """
        statuses = {}
        for service_name in self._registry.service_names:
            status = await self.get_service_status(service_name)
            if status:
                statuses[service_name] = status.to_dict()
        return statuses

    async def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all services.

        Returns:
            Summary dict with counts and lists.
        """
        health_map = await self._health_checker.check_all()

        healthy = [name for name, h in health_map.items() if h.is_healthy]
        unhealthy = [name for name, h in health_map.items() if not h.is_healthy]

        return {
            "total_services": self._registry.count,
            "healthy_count": len(healthy),
            "unhealthy_count": len(unhealthy),
            "healthy_services": healthy,
            "unhealthy_services": unhealthy,
            "auto_startable_count": len(self._registry.get_auto_startable()),
        }

    @property
    def service_count(self) -> int:
        """Get total number of managed services."""
        return self._registry.count

    @property
    def service_names(self) -> List[str]:
        """Get list of all service names."""
        return self._registry.service_names

    async def close(self) -> None:
        """Clean up resources."""
        await self._health_checker.close()


# Global singleton instance
_service_manager: Optional[ServiceManager] = None


def get_service_manager() -> ServiceManager:
    """Get the global ServiceManager instance (singleton)."""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager


def reset_service_manager() -> None:
    """Reset the global ServiceManager instance (for testing)."""
    global _service_manager
    _service_manager = None
