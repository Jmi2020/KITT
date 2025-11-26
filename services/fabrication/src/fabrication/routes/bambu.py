"""REST API endpoints for Bambu Labs printer integration."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..drivers.bambu_cloud import get_bambu_client, BambuToken

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bambu", tags=["bambu"])


class LoginRequest(BaseModel):
    """Login credentials."""

    email: str
    password: str


class VerifyRequest(BaseModel):
    """Verification code request."""

    email: str
    code: str


class CommandRequest(BaseModel):
    """Printer command request."""

    command: str  # pause, resume, stop


@router.get("/status")
async def token_status() -> dict[str, Any]:
    """Check if logged in to Bambu Labs cloud."""
    client = get_bambu_client()
    return {
        "logged_in": client.is_logged_in,
        "mqtt_connected": client.is_connected,
    }


@router.post("/login")
async def login(request: LoginRequest) -> dict[str, Any]:
    """
    Login to Bambu Labs cloud.

    Returns {"success": true} or {"error": str, "needs_verification": bool}
    """
    client = get_bambu_client()
    result = await client.login(request.email, request.password)

    if result.get("success"):
        # Start MQTT connection after login
        await client.fetch_printers()
        await client.connect_mqtt()

    return result


@router.post("/verify")
async def verify_code(request: VerifyRequest) -> dict[str, Any]:
    """Verify email code for passwordless login."""
    client = get_bambu_client()
    result = await client.verify_code(request.email, request.code)

    if result.get("success"):
        # Start MQTT connection after verification
        await client.fetch_printers()
        await client.connect_mqtt()

    return result


@router.post("/logout")
async def logout() -> dict[str, Any]:
    """Disconnect from Bambu Labs cloud."""
    client = get_bambu_client()
    client.disconnect()
    return {"success": True}


@router.get("/printers")
async def list_printers() -> list[dict[str, Any]]:
    """List connected Bambu Labs printers."""
    client = get_bambu_client()

    if not client.is_logged_in:
        raise HTTPException(status_code=401, detail="Not logged in to Bambu Labs")

    printers = client.get_printers()
    if not printers:
        printers = await client.fetch_printers()

    return [
        {
            "device_id": p.device_id,
            "name": p.name,
            "model": p.model,
            "online": p.online,
        }
        for p in printers
    ]


@router.get("/printers/{device_id}/telemetry")
async def get_telemetry(device_id: str) -> dict[str, Any]:
    """Get real-time telemetry for a printer."""
    client = get_bambu_client()

    if not client.is_logged_in:
        raise HTTPException(status_code=401, detail="Not logged in to Bambu Labs")

    telemetry = client.get_telemetry(device_id)
    if not telemetry:
        return {"error": "No telemetry available", "device_id": device_id}

    return {
        "device_id": telemetry.device_id,
        "gcode_state": telemetry.gcode_state,
        "percent": telemetry.percent,
        "remaining_time": telemetry.remaining_time,
        "bed_temp": telemetry.bed_temp,
        "bed_target": telemetry.bed_target,
        "nozzle_temp": telemetry.nozzle_temp,
        "nozzle_target": telemetry.nozzle_target,
        "fan_speed": telemetry.fan_speed,
        "layer_num": telemetry.layer_num,
        "total_layers": telemetry.total_layers,
        "ams_status": telemetry.ams_status,
        "last_update": telemetry.last_update,
    }


@router.get("/telemetry")
async def get_all_telemetry() -> dict[str, dict[str, Any]]:
    """Get telemetry for all connected printers."""
    client = get_bambu_client()

    if not client.is_logged_in:
        raise HTTPException(status_code=401, detail="Not logged in to Bambu Labs")

    telemetry = client.get_all_telemetry()
    return {
        device_id: {
            "device_id": t.device_id,
            "gcode_state": t.gcode_state,
            "percent": t.percent,
            "remaining_time": t.remaining_time,
            "bed_temp": t.bed_temp,
            "bed_target": t.bed_target,
            "nozzle_temp": t.nozzle_temp,
            "nozzle_target": t.nozzle_target,
            "fan_speed": t.fan_speed,
            "layer_num": t.layer_num,
            "total_layers": t.total_layers,
            "ams_status": t.ams_status,
            "last_update": t.last_update,
        }
        for device_id, t in telemetry.items()
    }


@router.post("/printers/{device_id}/command")
async def send_command(device_id: str, request: CommandRequest) -> dict[str, Any]:
    """
    Send control command to printer.

    Commands: pause, resume, stop
    """
    client = get_bambu_client()

    if not client.is_logged_in:
        raise HTTPException(status_code=401, detail="Not logged in to Bambu Labs")

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="MQTT not connected")

    success = await client.send_command(device_id, request.command)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to send command")

    return {"success": True, "device_id": device_id, "command": request.command}


@router.post("/connect")
async def connect_mqtt() -> dict[str, Any]:
    """Connect to Bambu Labs MQTT broker."""
    client = get_bambu_client()

    if not client.is_logged_in:
        raise HTTPException(status_code=401, detail="Not logged in to Bambu Labs")

    await client.fetch_printers()
    success = await client.connect_mqtt()

    return {"success": success, "connected": client.is_connected}
