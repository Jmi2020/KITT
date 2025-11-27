"""Print integration for CAD service - connects to Bambu printers."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cad", tags=["cad", "print"])

# Fabrication service URL (has Bambu integration)
FABRICATION_URL = os.getenv("FABRICATION_SERVICE_URL", "http://fabrication:8300")


class PrinterInfo(BaseModel):
    """Basic printer information."""

    device_id: str
    name: str
    model: str = ""
    online: bool = False
    status: str = "unknown"  # idle, printing, paused, error
    progress: int = 0
    bed_temp: float = 0.0
    nozzle_temp: float = 0.0


class PrintReadyResponse(BaseModel):
    """Response for print readiness check."""

    ready: bool
    printers: list[PrinterInfo]
    recommended_printer: Optional[str] = None
    message: str


class QueuePrintRequest(BaseModel):
    """Request to queue a model for printing."""

    artifact_path: str = Field(..., description="Path to STL/3MF file")
    printer_id: Optional[str] = Field(None, description="Target printer (auto-select if not provided)")
    material: Optional[str] = Field(None, description="Material type hint")
    profile: Optional[str] = Field("standard", description="Print profile")


class QueuePrintResponse(BaseModel):
    """Response from print queue request."""

    success: bool
    job_id: Optional[str] = None
    printer_id: Optional[str] = None
    message: str
    requires_slicing: bool = False
    slicer_url: Optional[str] = None


@router.get("/print-status", response_model=PrintReadyResponse)
async def get_print_status() -> PrintReadyResponse:
    """
    Check if any Bambu printers are available for printing.

    Use this after generating a model to show print options.
    """
    printers: list[PrinterInfo] = []
    recommended: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check Bambu cloud status
            status_resp = await client.get(f"{FABRICATION_URL}/api/bambu/status")
            if status_resp.status_code != 200:
                return PrintReadyResponse(
                    ready=False,
                    printers=[],
                    message="Bambu cloud not connected. Login at /api/bambu/login",
                )

            status = status_resp.json()
            if not status.get("logged_in"):
                return PrintReadyResponse(
                    ready=False,
                    printers=[],
                    message="Not logged in to Bambu Labs cloud",
                )

            # Get printer list with telemetry
            printers_resp = await client.get(f"{FABRICATION_URL}/api/bambu/printers")
            telemetry_resp = await client.get(f"{FABRICATION_URL}/api/bambu/telemetry")

            if printers_resp.status_code == 200:
                printer_list = printers_resp.json()
                telemetry = telemetry_resp.json() if telemetry_resp.status_code == 200 else {}

                for p in printer_list:
                    device_id = p.get("device_id", "")
                    telem = telemetry.get(device_id, {})

                    # Determine status from gcode_state
                    gcode_state = telem.get("gcode_state", "UNKNOWN")
                    if gcode_state in ("IDLE", "FINISH"):
                        status_str = "idle"
                    elif gcode_state in ("RUNNING", "PREPARE"):
                        status_str = "printing"
                    elif gcode_state == "PAUSE":
                        status_str = "paused"
                    else:
                        status_str = "unknown"

                    printer_info = PrinterInfo(
                        device_id=device_id,
                        name=p.get("name", "Unknown"),
                        model=p.get("model", ""),
                        online=p.get("online", False),
                        status=status_str,
                        progress=telem.get("percent", 0),
                        bed_temp=telem.get("bed_temp", 0.0),
                        nozzle_temp=telem.get("nozzle_temp", 0.0),
                    )
                    printers.append(printer_info)

                    # Recommend first idle online printer
                    if not recommended and printer_info.online and printer_info.status == "idle":
                        recommended = device_id

    except httpx.RequestError as e:
        logger.warning("Failed to contact fabrication service: %s", e)
        return PrintReadyResponse(
            ready=False,
            printers=[],
            message="Fabrication service unavailable",
        )

    has_ready = any(p.online and p.status == "idle" for p in printers)

    return PrintReadyResponse(
        ready=has_ready,
        printers=printers,
        recommended_printer=recommended,
        message="Printer ready" if has_ready else "No printers available",
    )


@router.post("/queue-print", response_model=QueuePrintResponse)
async def queue_print(request: QueuePrintRequest) -> QueuePrintResponse:
    """
    Queue a generated model for printing.

    Note: STL files need to be sliced first. This endpoint will:
    1. Check printer availability
    2. For STL: Return slicer URL (Bambu Studio handles slicing)
    3. For 3MF: Queue directly if pre-sliced
    """
    # Check file type
    is_stl = request.artifact_path.lower().endswith(".stl")
    is_3mf = request.artifact_path.lower().endswith(".3mf")

    if not (is_stl or is_3mf):
        raise HTTPException(
            status_code=400,
            detail="Only STL and 3MF files can be printed",
        )

    # Get printer status
    status = await get_print_status()

    if not status.ready:
        return QueuePrintResponse(
            success=False,
            message=status.message,
            requires_slicing=is_stl,
        )

    # Select printer
    printer_id = request.printer_id or status.recommended_printer
    if not printer_id:
        return QueuePrintResponse(
            success=False,
            message="No printer available",
            requires_slicing=is_stl,
        )

    # For STL files, we need to slice first
    if is_stl:
        # Generate Bambu Studio URL (local app) or web slicer link
        slicer_url = f"bambustudio://open?file={request.artifact_path}"

        return QueuePrintResponse(
            success=True,
            printer_id=printer_id,
            message="STL requires slicing. Open in Bambu Studio to slice and send to printer.",
            requires_slicing=True,
            slicer_url=slicer_url,
        )

    # For pre-sliced 3MF, we'd send directly (future enhancement)
    # Bambu cloud MQTT doesn't support direct file upload - need local LAN
    return QueuePrintResponse(
        success=True,
        printer_id=printer_id,
        message="3MF ready for printing. Use Bambu Studio to send to printer.",
        requires_slicing=False,
    )


@router.get("/ams-materials")
async def get_ams_materials() -> dict[str, Any]:
    """
    Get loaded AMS materials from connected Bambu printers.

    Useful for suggesting compatible materials when generating models.
    """
    materials: dict[str, list[dict]] = {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            telemetry_resp = await client.get(f"{FABRICATION_URL}/api/bambu/telemetry")

            if telemetry_resp.status_code == 200:
                telemetry = telemetry_resp.json()

                for device_id, telem in telemetry.items():
                    ams_status = telem.get("ams_status", {})
                    if ams_status:
                        # Extract material info from AMS
                        ams_list = ams_status.get("ams", [])
                        device_materials = []

                        for ams_unit in ams_list:
                            trays = ams_unit.get("tray", [])
                            for tray in trays:
                                if tray.get("tray_type"):
                                    device_materials.append({
                                        "slot": f"AMS{ams_unit.get('id', '?')}-{tray.get('id', '?')}",
                                        "type": tray.get("tray_type", "Unknown"),
                                        "color": tray.get("tray_color", ""),
                                        "remaining": tray.get("remain", -1),
                                    })

                        if device_materials:
                            materials[device_id] = device_materials

    except httpx.RequestError as e:
        logger.warning("Failed to get AMS materials: %s", e)

    return {
        "materials": materials,
        "has_materials": bool(materials),
    }
