# noqa: D401,D415
"""Conversational context models."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class DeviceSelection(BaseModel):
    """Represents the target device the user is currently referencing."""

    model_config = ConfigDict(extra="allow")

    device_id: str = Field(..., description="Internal device ID")
    friendly_name: str = Field(..., description="Human readable device label")
    zone_id: Optional[str] = Field(None, description="Zone in which the device resides")


class ConversationContext(BaseModel):
    """Shared conversational state persisted across endpoints."""

    model_config = ConfigDict(extra="allow")

    conversation_id: str
    last_intent: Optional[str] = None
    device: Optional[DeviceSelection] = None
    session_state: Dict[str, str] = Field(default_factory=dict)


__all__ = ["DeviceSelection", "ConversationContext"]
