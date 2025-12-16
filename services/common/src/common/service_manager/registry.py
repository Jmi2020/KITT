"""Service Registry for KITTY ServiceManager.

Central registry of all KITTY services with their configurations.
Services are defined here and can be overridden via environment variables.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from .types import HealthCheckType, ServiceDefinition, ServiceType

logger = logging.getLogger(__name__)

# Base path for KITTY project (detected from common location)
_KITTY_ROOT = Path(__file__).parents[6]  # services/common/src/common/service_manager -> root


def _is_running_in_docker() -> bool:
    """Detect if we're running inside a Docker container."""
    # Check for Docker-specific files/markers
    return (
        os.path.exists("/.dockerenv")
        or os.getenv("RUNNING_IN_DOCKER", "").lower() in ("true", "1", "yes")
    )


def _get_host_for_service(service_type: ServiceType, docker_service_name: Optional[str]) -> str:
    """Get the correct host for a service based on runtime environment.

    When running inside Docker:
    - Docker services should use their Docker DNS name (e.g., 'gateway', 'cad')
    - Native processes on host should use 'host.docker.internal'

    When running on host (not in Docker):
    - All services use 'localhost'
    """
    if not _is_running_in_docker():
        return "localhost"

    # Running inside Docker
    if service_type == ServiceType.NATIVE_PROCESS:
        # Native processes run on host, reach via host.docker.internal
        return "host.docker.internal"
    elif docker_service_name:
        # Docker services use their container DNS name
        return docker_service_name
    else:
        # Fallback (shouldn't happen for properly configured services)
        return "localhost"


def _get_env_bool(key: str, default: bool = True) -> bool:
    """Get boolean from environment variable."""
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


# Default service definitions
# NOTE: LLM services (Ollama, llama.cpp) are NOT included - managed by IdleReaper
_DEFAULT_SERVICES: List[ServiceDefinition] = [
    # Voice Service - Native process on host Mac
    ServiceDefinition(
        name="voice",
        display_name="Voice Service",
        service_type=ServiceType.NATIVE_PROCESS,
        port=_get_env_int("VOICE_PORT", 8410),
        host=_get_host_for_service(ServiceType.NATIVE_PROCESS, None),
        health_endpoint="/healthz",
        health_timeout_seconds=5.0,
        start_script=str(_KITTY_ROOT / "ops/scripts/start-voice-service.sh"),
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("VOICE_AUTO_START", True),
        env_port_var="VOICE_PORT",
    ),
    # Brain Service - Docker container (core orchestrator)
    # NOTE: Brain runs the ServiceManager, so it can't auto-start itself
    ServiceDefinition(
        name="brain",
        display_name="Brain Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8000,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "brain"),
        health_endpoint="/health",
        health_check_type=HealthCheckType.HTTP_JSON,
        docker_service_name="brain",
        startup_timeout_seconds=60.0,
        auto_start_enabled=False,  # Can't auto-start itself
    ),
    # Gateway Service - Docker container (API proxy, 3 replicas behind HAProxy)
    ServiceDefinition(
        name="gateway",
        display_name="Gateway (HAProxy)",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8080,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "load-balancer"),
        health_endpoint="/healthz",
        docker_service_name="load-balancer",  # Start HAProxy, which needs gateways
        startup_timeout_seconds=30.0,
        depends_on=["brain"],
        auto_start_enabled=_get_env_bool("GATEWAY_AUTO_START", True),
    ),
    # CAD Service - Docker container
    ServiceDefinition(
        name="cad",
        display_name="CAD Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8200,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "cad"),
        health_endpoint="/healthz",
        docker_service_name="cad",
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("CAD_AUTO_START", True),
    ),
    # Fabrication Service - Docker container
    ServiceDefinition(
        name="fabrication",
        display_name="Fabrication Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8300,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "fabrication"),
        health_endpoint="/healthz",
        docker_service_name="fabrication",
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("FABRICATION_AUTO_START", True),
    ),
    # Discovery Service - Docker container
    ServiceDefinition(
        name="discovery",
        display_name="Discovery Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8500,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "discovery"),
        health_endpoint="/healthz",
        docker_service_name="discovery",
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("DISCOVERY_AUTO_START", True),
    ),
    # Broker Service - Docker container
    ServiceDefinition(
        name="broker",
        display_name="Broker Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8777,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "broker"),
        health_endpoint="/healthz",
        docker_service_name="broker",
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("BROKER_AUTO_START", True),
    ),
    # Settings Service - Docker container
    ServiceDefinition(
        name="settings",
        display_name="Settings Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8450,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "settings"),
        health_endpoint="/healthz",
        docker_service_name="settings",
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("SETTINGS_AUTO_START", True),
    ),
    # Mem0-MCP Service - Docker container (semantic memory)
    ServiceDefinition(
        name="mem0-mcp",
        display_name="Memory Service",
        service_type=ServiceType.DOCKER_SERVICE,
        port=8765,
        host=_get_host_for_service(ServiceType.DOCKER_SERVICE, "mem0-mcp"),
        health_endpoint="/health",  # Uses /health, not /healthz
        docker_service_name="mem0-mcp",
        startup_timeout_seconds=30.0,
        auto_start_enabled=_get_env_bool("MEM0_AUTO_START", True),
    ),
    # Infrastructure services - Docker containers (don't auto-start, just monitor)
    ServiceDefinition(
        name="postgres",
        display_name="PostgreSQL",
        service_type=ServiceType.DOCKER_INFRA,
        port=5432,
        host=_get_host_for_service(ServiceType.DOCKER_INFRA, "postgres"),
        health_check_type=HealthCheckType.TCP_CONNECT,
        health_endpoint="",  # TCP check, no HTTP endpoint
        docker_service_name="postgres",
        auto_start_enabled=False,  # Don't auto-start infrastructure
    ),
    ServiceDefinition(
        name="redis",
        display_name="Redis",
        service_type=ServiceType.DOCKER_INFRA,
        port=6379,
        host=_get_host_for_service(ServiceType.DOCKER_INFRA, "redis"),
        health_check_type=HealthCheckType.TCP_CONNECT,
        health_endpoint="",
        docker_service_name="redis",
        auto_start_enabled=False,
    ),
    ServiceDefinition(
        name="rabbitmq",
        display_name="RabbitMQ",
        service_type=ServiceType.DOCKER_INFRA,
        port=5672,
        host=_get_host_for_service(ServiceType.DOCKER_INFRA, "rabbitmq"),
        health_check_type=HealthCheckType.TCP_CONNECT,
        health_endpoint="",
        docker_service_name="rabbitmq",
        auto_start_enabled=False,
    ),
    ServiceDefinition(
        name="mosquitto",
        display_name="MQTT Broker",
        service_type=ServiceType.DOCKER_INFRA,
        port=1883,
        host=_get_host_for_service(ServiceType.DOCKER_INFRA, "mosquitto"),
        health_check_type=HealthCheckType.TCP_CONNECT,
        health_endpoint="",
        docker_service_name="mosquitto",
        auto_start_enabled=False,
    ),
    ServiceDefinition(
        name="qdrant",
        display_name="Qdrant Vector DB",
        service_type=ServiceType.DOCKER_INFRA,
        port=6333,
        host=_get_host_for_service(ServiceType.DOCKER_INFRA, "qdrant"),
        health_endpoint="/",
        docker_service_name="qdrant",
        auto_start_enabled=False,
    ),
    ServiceDefinition(
        name="homeassistant",
        display_name="Home Assistant",
        service_type=ServiceType.DOCKER_INFRA,
        port=8123,
        host=_get_host_for_service(ServiceType.DOCKER_INFRA, "homeassistant"),
        health_check_type=HealthCheckType.TCP_CONNECT,  # API requires auth, just check TCP
        health_endpoint="",
        docker_service_name="homeassistant",
        auto_start_enabled=False,
    ),
]


class ServiceRegistry:
    """Central registry of all KITTY services.

    Provides access to service definitions and supports filtering
    by service type or auto-start capability.
    """

    def __init__(self, services: Optional[List[ServiceDefinition]] = None):
        """Initialize the registry with service definitions.

        Args:
            services: List of service definitions. Uses defaults if not provided.
        """
        self._services: Dict[str, ServiceDefinition] = {}
        for svc in services or _DEFAULT_SERVICES:
            self._services[svc.name] = svc
        logger.info(f"ServiceRegistry initialized with {len(self._services)} services")

    def get(self, name: str) -> Optional[ServiceDefinition]:
        """Get a service definition by name."""
        return self._services.get(name)

    def get_all(self) -> Dict[str, ServiceDefinition]:
        """Get all service definitions."""
        return self._services.copy()

    def get_by_type(self, service_type: ServiceType) -> List[ServiceDefinition]:
        """Get all services of a specific type."""
        return [s for s in self._services.values() if s.service_type == service_type]

    def get_auto_startable(self) -> List[ServiceDefinition]:
        """Get all services that can be auto-started."""
        return [s for s in self._services.values() if s.auto_start_enabled]

    def get_native_processes(self) -> List[ServiceDefinition]:
        """Get all native process services."""
        return self.get_by_type(ServiceType.NATIVE_PROCESS)

    def get_docker_services(self) -> List[ServiceDefinition]:
        """Get all Docker services (excluding infra)."""
        return self.get_by_type(ServiceType.DOCKER_SERVICE)

    def get_infrastructure(self) -> List[ServiceDefinition]:
        """Get all infrastructure services."""
        return self.get_by_type(ServiceType.DOCKER_INFRA)

    @property
    def service_names(self) -> List[str]:
        """Get list of all service names."""
        return list(self._services.keys())

    @property
    def count(self) -> int:
        """Get total number of services."""
        return len(self._services)


# Global registry instance
_registry: Optional[ServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    """Get the global ServiceRegistry instance (singleton)."""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry
