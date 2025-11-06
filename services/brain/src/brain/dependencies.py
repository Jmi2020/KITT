# noqa: D401
"""Dependency wiring for the brain service."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import SecretStr

from common.config import settings
from common.credentials import HomeAssistantCredentials
from common.messaging import MQTTClient

from safety.unifi.client import UniFiAccessClient
from safety.workflows.hazard import HazardWorkflow

from .orchestrator import BrainOrchestrator
from .routing.audit_store import RoutingAuditStore
from .routing.cost_tracker import CostTracker
from .routing.router import BrainRouter
from .metrics.slo import SLOCalculator
from .state.mqtt_context_store import MQTTContextStore


@lru_cache(maxsize=1)
def get_home_assistant_credentials() -> HomeAssistantCredentials:
    token = settings.home_assistant_token
    if not token:
        raise RuntimeError("HOME_ASSISTANT_TOKEN not configured")
    return HomeAssistantCredentials(
        token=SecretStr(token), base_url=settings.home_assistant_base_url
    )


@lru_cache(maxsize=1)
def get_context_store() -> MQTTContextStore:
    return MQTTContextStore(MQTTClient(client_id="brain"))  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_cost_tracker() -> CostTracker:
    return CostTracker()


@lru_cache(maxsize=1)
def get_slo_calculator() -> SLOCalculator:
    return SLOCalculator()


@lru_cache(maxsize=1)
def get_unifi_client() -> Optional[UniFiAccessClient]:
    try:
        return UniFiAccessClient()
    except RuntimeError:
        return None


@lru_cache(maxsize=1)
def get_hazard_workflow() -> HazardWorkflow:
    return HazardWorkflow(unifi_client=get_unifi_client())


@lru_cache(maxsize=1)
def get_orchestrator() -> BrainOrchestrator:
    router = BrainRouter(
        audit_store=RoutingAuditStore(),
        cost_tracker=get_cost_tracker(),
        slo_calculator=get_slo_calculator(),
    )
    return BrainOrchestrator(
        get_context_store(),
        get_home_assistant_credentials(),
        router,
        safety_workflow=get_hazard_workflow(),
    )


__all__ = ["get_orchestrator"]
