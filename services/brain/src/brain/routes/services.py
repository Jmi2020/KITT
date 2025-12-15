"""API routes for KITTY ServiceManager.

Provides endpoints for:
- Checking service health status
- Starting/stopping services
- On-demand service activation (ensure_running)
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])


class ServiceActionResponse(BaseModel):
    """Response for service action endpoints."""

    success: bool
    service: str
    message: Optional[str] = None


class ServiceHealthResponse(BaseModel):
    """Response for health check endpoints."""

    service_name: str
    is_healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


def _get_service_manager(request: Request):
    """Get ServiceManager from app state."""
    manager = getattr(request.app.state, "service_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="ServiceManager not initialized",
        )
    return manager


@router.get("/status")
async def get_all_service_status(request: Request) -> Dict[str, Any]:
    """Get health status of all managed services.

    Returns a dictionary mapping service names to their full status,
    including health, running state, and metadata.
    """
    manager = _get_service_manager(request)
    return await manager.get_all_status()


@router.get("/summary")
async def get_service_summary(request: Request) -> Dict[str, Any]:
    """Get a summary of all services.

    Returns counts of healthy/unhealthy services and lists.
    """
    manager = _get_service_manager(request)
    return await manager.get_summary()


@router.get("/status/{service_name}")
async def get_service_status(request: Request, service_name: str) -> Dict[str, Any]:
    """Get health status of a specific service.

    Args:
        service_name: Name of the service (e.g., "voice", "cad").

    Returns:
        Full status including health, running state, and metadata.
    """
    manager = _get_service_manager(request)
    status = await manager.get_service_status(service_name)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_name}",
        )
    return status.to_dict()


@router.get("/health/{service_name}")
async def check_service_health(
    request: Request, service_name: str
) -> ServiceHealthResponse:
    """Check health of a specific service.

    Performs an immediate health check (HTTP or TCP based on service type).

    Args:
        service_name: Name of the service to check.

    Returns:
        Health check result with latency and any error.
    """
    manager = _get_service_manager(request)
    health = await manager.check_health(service_name)
    if health is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_name}",
        )
    return ServiceHealthResponse(
        service_name=health.service_name,
        is_healthy=health.is_healthy,
        latency_ms=health.latency_ms,
        error=health.error,
    )


@router.post("/{service_name}/ensure")
async def ensure_service_running(
    request: Request, service_name: str
) -> ServiceActionResponse:
    """Ensure a service is running, starting it if necessary.

    This is the main on-demand activation endpoint. It:
    1. Checks if the service is already healthy
    2. If not, attempts to start it (if auto-start enabled)
    3. Waits for health check to pass

    Args:
        service_name: Name of the service to ensure is running.

    Returns:
        Action response indicating success or failure.
    """
    manager = _get_service_manager(request)
    success = await manager.ensure_running(service_name)

    if success:
        return ServiceActionResponse(
            success=True,
            service=service_name,
            message="Service is running",
        )
    else:
        return ServiceActionResponse(
            success=False,
            service=service_name,
            message="Failed to ensure service is running",
        )


@router.post("/{service_name}/start")
async def start_service(request: Request, service_name: str) -> ServiceActionResponse:
    """Manually start a service.

    Unlike ensure_running, this always attempts to start the service
    even if it's already running.

    Args:
        service_name: Name of the service to start.

    Returns:
        Action response indicating success or failure.
    """
    manager = _get_service_manager(request)
    success = await manager.start_service(service_name)

    return ServiceActionResponse(
        success=success,
        service=service_name,
        message="Service started" if success else "Failed to start service",
    )


@router.post("/{service_name}/stop")
async def stop_service(request: Request, service_name: str) -> ServiceActionResponse:
    """Stop a service.

    Args:
        service_name: Name of the service to stop.

    Returns:
        Action response indicating success or failure.
    """
    manager = _get_service_manager(request)
    success = await manager.stop_service(service_name)

    return ServiceActionResponse(
        success=success,
        service=service_name,
        message="Service stopped" if success else "Failed to stop service",
    )


@router.post("/{service_name}/restart")
async def restart_service(
    request: Request, service_name: str
) -> ServiceActionResponse:
    """Restart a service.

    Args:
        service_name: Name of the service to restart.

    Returns:
        Action response indicating success or failure.
    """
    manager = _get_service_manager(request)
    success = await manager.restart_service(service_name)

    return ServiceActionResponse(
        success=success,
        service=service_name,
        message="Service restarted" if success else "Failed to restart service",
    )


@router.get("/list")
async def list_services(request: Request) -> Dict[str, Any]:
    """List all managed services.

    Returns service names grouped by type.
    """
    manager = _get_service_manager(request)
    registry = manager._registry

    return {
        "total": registry.count,
        "services": registry.service_names,
        "native_processes": [s.name for s in registry.get_native_processes()],
        "docker_services": [s.name for s in registry.get_docker_services()],
        "infrastructure": [s.name for s in registry.get_infrastructure()],
        "auto_startable": [s.name for s in registry.get_auto_startable()],
    }
