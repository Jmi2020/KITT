"""
Network Discovery Service FastAPI application.

Provides REST API for device discovery, registry management, and scanning.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .models import (
    ApproveDeviceRequest,
    ApproveDeviceResponse,
    DeviceListResponse,
    DeviceResponse,
    RejectDeviceRequest,
    RejectDeviceResponse,
    ScanRequest,
    ScanStatusResponse,
)

try:
    from common.config import Settings
except ImportError:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        """Fallback settings if common package not available."""
        postgres_url: str = os.getenv(
            "POSTGRES_URL",
            "postgresql+asyncpg://kitty:changeme@postgres:5432/kitty"
        )
        discovery_port: int = int(os.getenv("DISCOVERY_PORT", "8500"))
        discovery_scan_interval_minutes: int = int(
            os.getenv("DISCOVERY_SCAN_INTERVAL_MINUTES", "15")
        )
        discovery_enable_periodic_scans: bool = (
            os.getenv("DISCOVERY_ENABLE_PERIODIC_SCANS", "true").lower() == "true"
        )

from .registry.device_store import DeviceStore
from .scheduler.scan_scheduler import ScanScheduler

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global state
device_store: Optional[DeviceStore] = None
scan_scheduler: Optional[ScanScheduler] = None
settings: Optional[Settings] = None


class ArpIngestEntry(BaseModel):
    ip_address: str
    mac_address: str
    vendor: Optional[str] = None


class ArpIngestRequest(BaseModel):
    entries: list[ArpIngestEntry]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global device_store, scan_scheduler, settings

    # Initialize settings
    settings = Settings()

    # Build PostgreSQL URL from settings
    postgres_url = (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    # Initialize device store
    device_store = DeviceStore(postgres_url)
    logger.info("Device store initialized")

    # Build list of enabled scanners from settings
    enabled_scanners = []
    if settings.discovery_enable_mdns:
        enabled_scanners.append("mdns")
    if settings.discovery_enable_ssdp:
        enabled_scanners.append("ssdp")
    if settings.discovery_enable_bamboo_udp:
        enabled_scanners.append("bamboo_udp")
    if settings.discovery_enable_snapmaker_udp:
        enabled_scanners.append("snapmaker_udp")
    if settings.discovery_enable_network_scan:
        enabled_scanners.append("network_scan")

    logger.info(f"Enabled scanners: {enabled_scanners}")
    logger.info(f"Ping sweep subnets: {settings.discovery_subnets}")

    # Initialize scan scheduler
    scan_scheduler = ScanScheduler(
        device_store=device_store,
        interval_minutes=settings.discovery_scan_interval_minutes,
        ping_sweep_interval_minutes=settings.discovery_ping_sweep_interval_minutes,
        enabled_scanners=enabled_scanners,
        subnets=settings.discovery_subnets
    )

    # Start periodic scans if enabled
    if settings.discovery_enable_periodic_scans:
        await scan_scheduler.start()
        logger.info("Periodic scans started")

    yield

    # Cleanup
    if scan_scheduler:
        await scan_scheduler.stop()
        logger.info("Scan scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title="Network Discovery Service",
    description="IoT device discovery and registry management",
    version="1.0.0",
    lifespan=lifespan
)


# ==============================================================================
# Health Check
# ==============================================================================

@app.get("/healthz")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# ==============================================================================
# ARP Ingest
# ==============================================================================

@app.post("/api/discovery/arp")
async def ingest_arp(body: ArpIngestRequest) -> Dict[str, Any]:
    """
    Ingest ARP scan results (IP/MAC/vendor) from a host-side scan.

    This endpoint expects trusted input (no auth implemented here).
    """
    try:
        if not device_store:
            raise HTTPException(status_code=500, detail="Device store not initialized")

        count = 0
        for entry in body.entries:
            try:
                await device_store.upsert_manual_device(
                    ip_address=entry.ip_address,
                    mac_address=entry.mac_address,
                    vendor_hint=entry.vendor,
                    discovery_method="arp_scan",
                )
                count += 1
            except Exception as e:
                logger.error(f"Failed to upsert ARP entry {entry.ip_address}: {e}")

        return {"ingested": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ARP ingest failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Discovery Scan Control
# ==============================================================================

@app.post("/api/discovery/scan", response_model=ScanStatusResponse)
async def trigger_scan(request: ScanRequest) -> ScanStatusResponse:
    """
    Trigger a manual network discovery scan.

    Args:
        request: Scan parameters (methods, timeout)

    Returns:
        Scan status with scan_id for tracking
    """
    try:
        scan_id = await scan_scheduler.trigger_manual_scan(
            methods=request.methods,
            timeout_seconds=request.timeout_seconds
        )

        # Get scan record
        scan_record = await device_store.get_scan_record(UUID(scan_id))

        return ScanStatusResponse(
            scan_id=scan_record.id,
            status=scan_record.status,
            started_at=scan_record.started_at,
            methods=scan_record.methods,
            devices_found=scan_record.devices_found
        )

    except Exception as e:
        logger.error(f"Failed to trigger scan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discovery/scan/{scan_id}", response_model=ScanStatusResponse)
async def get_scan_status(scan_id: UUID) -> ScanStatusResponse:
    """
    Get status of a discovery scan.

    Args:
        scan_id: Scan UUID

    Returns:
        Scan status and results
    """
    scan_record = await device_store.get_scan_record(scan_id)

    if not scan_record:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanStatusResponse(
        scan_id=scan_record.id,
        status=scan_record.status,
        started_at=scan_record.started_at,
        completed_at=scan_record.completed_at,
        methods=scan_record.methods,
        devices_found=scan_record.devices_found,
        errors=scan_record.errors or []
    )


# ==============================================================================
# Device Registry
# ==============================================================================

@app.get("/api/discovery/devices", response_model=DeviceListResponse)
async def list_devices(
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    approved: Optional[bool] = Query(None, description="Filter by approval status"),
    is_online: Optional[bool] = Query(None, description="Filter by online status"),
    manufacturer: Optional[str] = Query(None, description="Filter by manufacturer"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Results offset")
) -> DeviceListResponse:
    """
    List discovered devices with optional filters.

    Args:
        device_type: Filter by device type
        approved: Filter by approval status
        is_online: Filter by online status
        manufacturer: Filter by manufacturer
        limit: Max results
        offset: Results offset

    Returns:
        List of devices and total count
    """
    try:
        devices, total = await device_store.list_devices(
            device_type=device_type,
            approved=approved,
            is_online=is_online,
            manufacturer=manufacturer,
            limit=limit,
            offset=offset
        )

        device_responses = [DeviceResponse.model_validate(d) for d in devices]

        filters_applied = {}
        if device_type:
            filters_applied["device_type"] = device_type
        if approved is not None:
            filters_applied["approved"] = approved
        if is_online is not None:
            filters_applied["is_online"] = is_online
        if manufacturer:
            filters_applied["manufacturer"] = manufacturer

        return DeviceListResponse(
            devices=device_responses,
            total=total,
            filters_applied=filters_applied
        )

    except Exception as e:
        logger.error(f"Failed to list devices: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discovery/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: UUID) -> DeviceResponse:
    """
    Get device details by ID.

    Args:
        device_id: Device UUID

    Returns:
        Device information
    """
    device = await device_store.get_device(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return DeviceResponse.model_validate(device)


@app.get("/api/discovery/search", response_model=DeviceListResponse)
async def search_devices(
    q: str = Query(..., description="Search query (hostname, model, manufacturer, IP)"),
    limit: int = Query(50, ge=1, le=500, description="Max results")
) -> DeviceListResponse:
    """
    Search devices by hostname, model, manufacturer, or IP address.

    Args:
        q: Search query
        limit: Max results

    Returns:
        List of matching devices
    """
    try:
        devices = await device_store.search_devices(query=q, limit=limit)

        device_responses = [DeviceResponse.model_validate(d) for d in devices]

        return DeviceListResponse(
            devices=device_responses,
            total=len(device_responses),
            filters_applied={"query": q}
        )

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discovery/printers", response_model=DeviceListResponse)
async def list_printers() -> DeviceListResponse:
    """
    List all discovered printers (3D, CNC, laser).

    Returns:
        List of printer devices
    """
    try:
        # Get all printer types
        printer_types = ["printer_3d", "printer_cnc", "printer_laser"]
        all_printers = []

        for device_type in printer_types:
            devices, _ = await device_store.list_devices(
                device_type=device_type,
                limit=100
            )
            all_printers.extend(devices)

        device_responses = [DeviceResponse.model_validate(d) for d in all_printers]

        return DeviceListResponse(
            devices=device_responses,
            total=len(device_responses),
            filters_applied={"device_type": "printer_*"}
        )

    except Exception as e:
        logger.error(f"Failed to list printers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Device Approval
# ==============================================================================

@app.post("/api/discovery/devices/{device_id}/approve", response_model=ApproveDeviceResponse)
async def approve_device(
    device_id: UUID,
    request: ApproveDeviceRequest
) -> ApproveDeviceResponse:
    """
    Approve a device for integration and control.

    Args:
        device_id: Device UUID
        request: Approval notes

    Returns:
        Updated device approval status
    """
    try:
        # For now, use "admin" as approver (TODO: integrate with auth)
        approved_by = "admin"

        device = await device_store.approve_device(
            device_id=device_id,
            approved_by=approved_by,
            notes=request.notes
        )

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        return ApproveDeviceResponse(
            id=device.id,
            approved=device.approved,
            approved_at=device.approved_at,
            approved_by=device.approved_by
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve device: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/discovery/devices/{device_id}/reject", response_model=RejectDeviceResponse)
async def reject_device(
    device_id: UUID,
    request: RejectDeviceRequest
) -> RejectDeviceResponse:
    """
    Reject/unapprove a device.

    Args:
        device_id: Device UUID
        request: Rejection notes

    Returns:
        Updated device status
    """
    try:
        # For now, use "admin" as rejector (TODO: integrate with auth)
        rejected_by = "admin"

        device = await device_store.reject_device(
            device_id=device_id,
            rejected_by=rejected_by,
            notes=request.notes
        )

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        return RejectDeviceResponse(
            id=device.id,
            approved=device.approved,
            notes=device.notes
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject device: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/discovery/devices/{device_id}")
async def delete_device(device_id: UUID) -> Dict[str, Any]:
    """
    Delete a device from the registry.

    Args:
        device_id: Device UUID

    Returns:
        Success message
    """
    try:
        success = await device_store.delete_device(device_id)

        if not success:
            raise HTTPException(status_code=404, detail="Device not found")

        return {"success": True, "message": "Device removed from registry"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete device: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Error Handlers
# ==============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# ==============================================================================
# ARP Ingest (optional host-privileged scan)
# ==============================================================================

@app.post("/api/discovery/arp")
async def ingest_arp(body: ArpIngestRequest) -> Dict[str, Any]:
    """
    Ingest ARP scan results (IP/MAC/vendor) from a host-side scan.

    This endpoint expects trusted input (no auth implemented here).
    """
    try:
        if not device_store:
            raise HTTPException(status_code=500, detail="Device store not initialized")

        count = 0
        for entry in body.entries:
            try:
                await device_store.upsert_manual_device(
                    ip_address=entry.ip_address,
                    mac_address=entry.mac_address,
                    vendor_hint=entry.vendor,
                    discovery_method="arp_scan",
                )
                count += 1
            except Exception as e:
                logger.error(f"Failed to upsert ARP entry {entry.ip_address}: {e}")

        return {"ingested": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ARP ingest failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("DISCOVERY_PORT", "8500"))
    uvicorn.run(app, host="0.0.0.0", port=port)
