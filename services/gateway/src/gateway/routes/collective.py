
from __future__ import annotations
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

router = APIRouter(prefix="/api/collective", tags=["collective"])

# KITTY uses brain service on port 8000, not agent-runtime
BASE = "http://brain:8000/api/collective"

class RunReq(BaseModel):
    task: str
    pattern: Literal["pipeline","council","debate"] = "pipeline"
    k: int = Field(3, ge=2, le=7)
    max_steps: int = Field(8, ge=1, le=20)

@router.post("/run")
async def proxy_run(req: RunReq):
    """Proxy collective meta-agent requests to brain service.

    Forwards requests to brain:8000/api/collective/run which executes
    the collective meta-agent patterns (council, debate, pipeline).

    This allows external clients to access the collective functionality
    through the gateway's public interface.
    """
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{BASE}/run", json=req.dict())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
