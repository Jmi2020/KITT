"""Device command routes."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from common.messaging import MQTTClient, PublishOptions

router = APIRouter(prefix="/api/device", tags=["devices"])

mqtt_client = MQTTClient(client_id="gateway")
mqtt_client.connect()


class CommandRequest(BaseModel):
    intent: str
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.post("/{device_id}/command")
async def command_device(device_id: str = Path(...), body: CommandRequest | None = None) -> Dict[str, str]:
    if not body:
        raise HTTPException(status_code=400, detail="Missing body")
    topic = f"kitty/devices/{device_id}/cmd"
    mqtt_client.publish(
        topic,
        {"deviceId": device_id, "intent": body.intent, **body.payload},
        options=PublishOptions(qos=1, retain=False),
    )
    return {"status": "queued"}
