"""Remote status routes for KITTY."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/remote", tags=["Remote"])


@router.get("/status")
async def remote_status(request: Request) -> dict:
    forced = os.environ.get("KITTY_REMOTE_MODE")
    if forced:
        return {"remote": forced.lower() == "true", "reason": "env"}

    header_mode = request.headers.get("X-Remote-Mode")
    if header_mode:
        return {"remote": header_mode.lower() == "read-only", "reason": "header"}

    client_host = request.client.host if request.client else "local"
    is_remote = client_host not in {"127.0.0.1", "::1"}
    return {"remote": is_remote, "reason": "client"}
