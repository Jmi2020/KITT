
from __future__ import annotations
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

router = APIRouter(prefix="/api/collective", tags=["collective"])
BASE = "http://agent-runtime:8093/api/collective"

class RunReq(BaseModel):
    task: str
    pattern: Literal["pipeline","council","debate"] = "pipeline"
    k: int = Field(3, ge=2, le=7)
    max_steps: int = Field(8, ge=1, le=20)

@router.post("/run")
async def proxy_run(req: RunReq):
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{BASE}/run", json=req.dict())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
