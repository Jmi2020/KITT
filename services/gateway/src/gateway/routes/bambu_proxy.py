"""
KITTY Gateway - Bambu Labs Proxy
Proxies Bambu Labs cloud API requests to the fabrication service
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Response
import httpx


router = APIRouter(prefix="/api/bambu", tags=["bambu"])

FABRICATION_BASE = os.getenv("FABRICATION_BASE", "http://localhost:8300")


async def _proxy_to_fabrication(method: str, path: str, request: Request | None = None) -> Any:
    """Proxy request to fabrication service."""
    url = f"{FABRICATION_BASE}/api/bambu{path}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                data = await request.json() if request else {}
                response = await client.post(url, json=data)
            else:
                raise HTTPException(status_code=405, detail="Method not allowed")

            # Return JSON response
            try:
                return response.json()
            except Exception:
                return {"error": response.text, "status_code": response.status_code}

        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Fabrication service unavailable. Is it running on port 8300?"
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/status")
async def bambu_status() -> dict[str, Any]:
    """Check Bambu Labs login status."""
    return await _proxy_to_fabrication("GET", "/status")


@router.post("/login")
async def bambu_login(request: Request) -> dict[str, Any]:
    """Login to Bambu Labs cloud."""
    return await _proxy_to_fabrication("POST", "/login", request)


@router.post("/verify")
async def bambu_verify(request: Request) -> dict[str, Any]:
    """Verify email code for Bambu Labs login."""
    return await _proxy_to_fabrication("POST", "/verify", request)


@router.post("/logout")
async def bambu_logout() -> dict[str, Any]:
    """Logout from Bambu Labs cloud."""
    return await _proxy_to_fabrication("POST", "/logout")


@router.get("/printers")
async def bambu_printers() -> list[dict[str, Any]]:
    """List Bambu Labs printers."""
    return await _proxy_to_fabrication("GET", "/printers")


@router.get("/printers/{device_id}/telemetry")
async def bambu_telemetry(device_id: str) -> dict[str, Any]:
    """Get telemetry for a specific printer."""
    return await _proxy_to_fabrication("GET", f"/printers/{device_id}/telemetry")


@router.get("/telemetry")
async def bambu_all_telemetry() -> dict[str, dict[str, Any]]:
    """Get telemetry for all printers."""
    return await _proxy_to_fabrication("GET", "/telemetry")


@router.post("/printers/{device_id}/command")
async def bambu_command(device_id: str, request: Request) -> dict[str, Any]:
    """Send command to a Bambu printer."""
    url = f"{FABRICATION_BASE}/api/bambu/printers/{device_id}/command"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            data = await request.json()
            response = await client.post(url, json=data)
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Fabrication service unavailable"
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect")
async def bambu_connect() -> dict[str, Any]:
    """Reconnect to Bambu MQTT broker."""
    return await _proxy_to_fabrication("POST", "/connect")
