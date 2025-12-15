"""Type definitions for KITTY ServiceManager.

This module defines the core data structures for service management,
including service definitions, health status, and enums.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ServiceType(Enum):
    """Type of service for different management strategies."""

    NATIVE_PROCESS = "native_process"  # Voice service, runs as uvicorn process
    DOCKER_SERVICE = "docker_service"  # Brain, Gateway, CAD, etc.
    DOCKER_INFRA = "docker_infra"  # Postgres, Redis (don't auto-start these)


class HealthCheckType(Enum):
    """How to check if a service is healthy."""

    HTTP_GET = "http_get"  # GET endpoint, expect 200
    HTTP_JSON = "http_json"  # GET endpoint, parse JSON for status field
    TCP_CONNECT = "tcp_connect"  # Just check if port is open


@dataclass
class ServiceDefinition:
    """Definition of a KITTY service for management.

    Attributes:
        name: Unique identifier (e.g., "voice", "cad")
        display_name: Human-readable name
        service_type: How the service runs (native, docker, infra)
        port: Port the service listens on
        host: Hostname (default: localhost)
        health_check_type: How to check health
        health_endpoint: URL path for health check
        health_timeout_seconds: Timeout for health check requests
        start_script: Path to startup script (for native processes)
        docker_service_name: Service name in docker-compose.yml
        startup_timeout_seconds: Max time to wait for service to become healthy
        depends_on: Services that must be running first
        auto_start_enabled: Whether ServiceManager can auto-start this
        env_port_var: Environment variable that overrides the port
    """

    name: str
    display_name: str
    service_type: ServiceType
    port: int
    host: str = "localhost"
    health_check_type: HealthCheckType = HealthCheckType.HTTP_GET
    health_endpoint: str = "/healthz"
    health_timeout_seconds: float = 5.0
    start_script: Optional[str] = None
    docker_service_name: Optional[str] = None
    startup_timeout_seconds: float = 60.0
    depends_on: List[str] = field(default_factory=list)
    auto_start_enabled: bool = True
    env_port_var: Optional[str] = None

    @property
    def base_url(self) -> str:
        """Get the base URL for this service."""
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        """Get the full health check URL."""
        return f"{self.base_url}{self.health_endpoint}"


@dataclass
class HealthStatus:
    """Result of a health check for a service.

    Attributes:
        service_name: Name of the service checked
        is_healthy: Whether the service is healthy
        checked_at: When the check was performed
        latency_ms: Response time in milliseconds (if successful)
        status_code: HTTP status code (if HTTP check)
        error: Error message (if check failed)
        details: Additional details from health response
    """

    service_name: str
    is_healthy: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "service_name": self.service_name,
            "is_healthy": self.is_healthy,
            "checked_at": self.checked_at.isoformat(),
            "latency_ms": self.latency_ms,
            "status_code": self.status_code,
            "error": self.error,
            "details": self.details,
        }


@dataclass
class ServiceStatus:
    """Overall status of a service including health and metadata.

    Attributes:
        service: The service definition
        health: Latest health check result
        is_running: Whether the service process/container is running
        pid: Process ID (for native processes)
        container_id: Docker container ID (for Docker services)
        uptime_seconds: How long the service has been running
        last_started_at: When the service was last started
    """

    service: ServiceDefinition
    health: Optional[HealthStatus] = None
    is_running: bool = False
    pid: Optional[int] = None
    container_id: Optional[str] = None
    uptime_seconds: Optional[float] = None
    last_started_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.service.name,
            "display_name": self.service.display_name,
            "type": self.service.service_type.value,
            "port": self.service.port,
            "base_url": self.service.base_url,
            "is_running": self.is_running,
            "is_healthy": self.health.is_healthy if self.health else False,
            "health": self.health.to_dict() if self.health else None,
            "pid": self.pid,
            "container_id": self.container_id,
            "uptime_seconds": self.uptime_seconds,
            "last_started_at": (
                self.last_started_at.isoformat() if self.last_started_at else None
            ),
            "auto_start_enabled": self.service.auto_start_enabled,
        }
