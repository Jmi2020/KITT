"""Hazard workflow engine."""

from __future__ import annotations

from typing import Optional

from common.db.models import RoutingTier, SafetyEventStatus, SafetyEventType
from common.logging import get_logger

from .. import audit
from ..policies import HazardPolicy, get_policy
from ..signing import verify_signature
from ..unifi.client import UniFiAccessClient

LOGGER = get_logger(__name__)


class HazardWorkflow:
    def __init__(self, unifi_client: Optional[UniFiAccessClient] = None) -> None:
        self._unifi = unifi_client

    async def process_device_intent(
        self,
        *,
        intent: str,
        device_id: Optional[str],
        zone_id: Optional[str],
        user_id: str,
        signature: Optional[str],
    ) -> tuple[bool, dict]:
        policy = get_policy(intent)
        if not policy:
            return True, {"status": "allowed"}

        payload = f"{intent}:{device_id}:{zone_id}:{user_id}"
        if not signature or not verify_signature(payload, signature):
            LOGGER.warning("Hazard signature invalid", intent=intent, user=user_id)
            return False, {"status": "error", "message": "invalid signature"}

        if policy.requires_presence and self._unifi and zone_id:
            presence = await self._unifi.get_zone_presence(zone_id)
            if not presence.get("occupied"):
                LOGGER.info("Zone not occupied", zone=zone_id)
                return False, {"status": "denied", "reason": "zone not occupied"}

        event = audit.create_event(
            event_type=SafetyEventType.hazard_request,
            device_id=device_id,
            zone_id=zone_id,
            initiated_by=user_id,
            signature=signature,
        )

        if policy.requires_dual_confirm:
            LOGGER.info("Hazard action pending secondary approval", event=event.id)
            return False, {"status": "pending_approval", "eventId": event.id}

        audit.update_event(event.id, approved_by=user_id, status=SafetyEventStatus.approved)
        LOGGER.info("Hazard action auto-approved", event=event.id)
        return True, {"status": "approved", "eventId": event.id}

    async def approve_event(self, event_id: str, approver_id: str) -> dict:
        audit.update_event(event_id, approved_by=approver_id, status=SafetyEventStatus.approved)
        return {"status": "approved", "eventId": event_id}
