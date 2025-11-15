"""FastAPI entrypoint for the KITTY safety service."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from common.logging import get_logger

from .workflows.hazard import HazardWorkflow

LOGGER = get_logger(__name__)
app = FastAPI(title="KITTY Safety Service", version="0.1.0")


def get_workflow() -> HazardWorkflow:
    """Resolve the hazard workflow (UniFi client optional)."""
    # UniFi client wiring lives in hazard workflow; we keep the default for now.
    return HazardWorkflow()


class HazardRequest(BaseModel):
    intent: str
    deviceId: Optional[str] = None
    zoneId: Optional[str] = None
    userId: str
    signature: Optional[str] = None


class HazardResponse(BaseModel):
    status: str
    eventId: Optional[str] = None
    allowed: bool = False
    message: Optional[str] = None


class ApprovalRequest(BaseModel):
    eventId: str
    approverId: str


@app.get("/health")
async def health() -> dict[str, str]:
    """Readiness probe used by Docker compose."""
    return {"status": "ok"}


@app.post("/api/safety/hazards", response_model=HazardResponse)
async def handle_hazard(
    request: HazardRequest, workflow: HazardWorkflow = Depends(get_workflow)
) -> HazardResponse:
    """Process a potentially hazardous device intent."""
    allowed, payload = await workflow.process_device_intent(
        intent=request.intent,
        device_id=request.deviceId,
        zone_id=request.zoneId,
        user_id=request.userId,
        signature=request.signature,
    )

    if payload.get("status") == "error":
        raise HTTPException(status_code=403, detail=payload.get("message", "denied"))

    return HazardResponse(
        status=payload.get("status", "unknown"),
        eventId=payload.get("eventId"),
        allowed=allowed,
        message=payload.get("reason"),
    )


@app.post("/api/safety/hazards/approve", response_model=dict)
async def approve_hazard(
    request: ApprovalRequest, workflow: HazardWorkflow = Depends(get_workflow)
) -> dict:
    """Approve a pending hazard event."""
    LOGGER.info("Approving hazard event", event=request.eventId, approver=request.approverId)
    return await workflow.approve_event(request.eventId, request.approverId)
