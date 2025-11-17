# noqa: D401
"""Dependency wiring for the brain service."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from pydantic import SecretStr

from common.config import settings
from common.credentials import HomeAssistantCredentials
from common.mqtt import MQTTClient

from .orchestrator import BrainOrchestrator
from .routing.audit_store import RoutingAuditStore
from .routing.cost_tracker import CostTracker
from .routing.router import BrainRouter
from .metrics.slo import SLOCalculator
from .state.mqtt_context_store import MQTTContextStore
from .agents.graphs.integration import LangGraphRoutingIntegration
from .memory import MemoryClient

logger = logging.getLogger(__name__)


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
def get_unifi_client() -> Optional[object]:
    """Get UniFi client if safety service is available."""
    try:
        from safety.unifi.client import UniFiAccessClient

        return UniFiAccessClient()
    except (ImportError, RuntimeError):
        return None


@lru_cache(maxsize=1)
def get_hazard_workflow() -> Optional[object]:
    """Get hazard workflow if safety service is available."""
    try:
        from safety.workflows.hazard import HazardWorkflow

        return HazardWorkflow(unifi_client=get_unifi_client())
    except ImportError:
        return None


@lru_cache(maxsize=1)
def get_langgraph_integration() -> Optional[LangGraphRoutingIntegration]:
    """Get LangGraph integration if enabled.

    Returns:
        LangGraphRoutingIntegration if feature flag is enabled, None otherwise
    """
    import os

    if os.getenv("BRAIN_USE_LANGGRAPH", "false").lower() != "true":
        logger.info("LangGraph integration disabled (BRAIN_USE_LANGGRAPH=false)")
        return None

    logger.info("Initializing LangGraph integration")

    # Create a router to get access to its clients
    router = BrainRouter(
        audit_store=RoutingAuditStore(),
        cost_tracker=get_cost_tracker(),
        slo_calculator=get_slo_calculator(),
    )

    # Create integration with router's clients
    integration = LangGraphRoutingIntegration(
        llm_client=router._llama,
        memory_client=MemoryClient(),
        mcp_client=router._tool_mcp,
    )

    return integration


@lru_cache(maxsize=1)
def get_orchestrator() -> BrainOrchestrator:
    router = BrainRouter(
        audit_store=RoutingAuditStore(),
        cost_tracker=get_cost_tracker(),
        slo_calculator=get_slo_calculator(),
    )

    # Get LangGraph integration if enabled
    langgraph = get_langgraph_integration()

    # Get persistent conversation state manager if available (from app.state)
    # Falls back to in-memory manager if not initialized
    state_manager = None
    try:
        from .app import app
        state_manager = getattr(app.state, "conversation_state_manager", None)
        if state_manager:
            logger.info("Using persistent conversation state manager")
    except Exception as e:
        logger.warning(f"Persistent state manager not available: {e}, using in-memory")

    return BrainOrchestrator(
        get_context_store(),
        get_home_assistant_credentials(),
        router,
        safety_workflow=get_hazard_workflow(),
        langgraph_integration=langgraph,
        state_manager=state_manager,
    )


__all__ = ["get_orchestrator"]
