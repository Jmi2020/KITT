"""KITTY ServiceManager - Dynamic service health monitoring and on-demand activation.

This module provides a unified service management system for KITTY that:
- Monitors health of all services (native processes and Docker containers)
- Auto-starts services on-demand when they're needed but not running
- Provides API for status reporting and manual control

Usage:
    from common.service_manager import get_service_manager

    # Get the global manager instance
    manager = get_service_manager()

    # Check if a service is healthy
    health = await manager.check_health("voice")

    # Ensure a service is running (auto-starts if needed)
    success = await manager.ensure_running("voice")

    # Get all service statuses
    statuses = await manager.get_all_status()

Note: LLM servers (Ollama, llama.cpp) are managed by IdleReaper, not ServiceManager.
"""

from .docker_starter import DockerStarter
from .health_checker import HealthChecker
from .manager import ServiceManager, get_service_manager, reset_service_manager
from .native_starter import NativeStarter
from .registry import ServiceRegistry, get_registry
from .types import (
    HealthCheckType,
    HealthStatus,
    ServiceDefinition,
    ServiceStatus,
    ServiceType,
)

__all__ = [
    # Main classes
    "ServiceManager",
    "ServiceRegistry",
    "HealthChecker",
    "NativeStarter",
    "DockerStarter",
    # Type classes
    "ServiceDefinition",
    "ServiceType",
    "HealthCheckType",
    "HealthStatus",
    "ServiceStatus",
    # Singleton accessors
    "get_service_manager",
    "get_registry",
    "reset_service_manager",
]
