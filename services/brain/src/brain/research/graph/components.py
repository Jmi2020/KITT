"""
Research Graph Component Factory

Provides dependency injection for research graph nodes.
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ResearchComponents:
    """
    Container for all research infrastructure components.

    Provides dependency injection for graph nodes, enabling:
    - Real tool execution via ResearchToolExecutor
    - Permission checks via UnifiedPermissionGate
    - Model consultation via ModelCoordinator
    - Budget tracking via BudgetManager
    """

    # Core execution components
    tool_executor: Optional[any] = None  # ResearchToolExecutor
    permission_gate: Optional[any] = None  # UnifiedPermissionGate
    model_coordinator: Optional[any] = None  # ModelCoordinator
    budget_manager: Optional[any] = None  # BudgetManager

    # MCP servers (if needed directly)
    research_server: Optional[any] = None  # ResearchMCPServer
    memory_server: Optional[any] = None  # MemoryMCPServer

    # I/O Control
    io_control: Optional[any] = None  # FeatureStateManager

    def is_fully_wired(self) -> bool:
        """Check if all core components are initialized"""
        return all([
            self.tool_executor is not None,
            self.permission_gate is not None,
            self.model_coordinator is not None,
            self.budget_manager is not None
        ])

    def get_status(self) -> dict:
        """Get component initialization status"""
        return {
            "tool_executor": self.tool_executor is not None,
            "permission_gate": self.permission_gate is not None,
            "model_coordinator": self.model_coordinator is not None,
            "budget_manager": self.budget_manager is not None,
            "research_server": self.research_server is not None,
            "memory_server": self.memory_server is not None,
            "io_control": self.io_control is not None,
            "fully_wired": self.is_fully_wired()
        }


# Global components instance (set during brain service startup)
_components: Optional[ResearchComponents] = None


def set_global_components(components: ResearchComponents):
    """
    Set global research components.

    Called during brain service startup to inject components into graph nodes.

    Args:
        components: ResearchComponents instance with initialized dependencies
    """
    global _components
    _components = components

    status = components.get_status()
    logger.info(f"Research components registered: {status}")

    if not components.is_fully_wired():
        logger.warning("Not all core components are initialized - graph may use fallbacks")


def get_global_components() -> Optional[ResearchComponents]:
    """
    Get global research components.

    Returns:
        ResearchComponents instance or None if not set
    """
    return _components


def require_components() -> ResearchComponents:
    """
    Get components or raise error if not set.

    Returns:
        ResearchComponents instance

    Raises:
        RuntimeError: If components not initialized
    """
    if _components is None:
        raise RuntimeError(
            "Research components not initialized. "
            "Call set_global_components() during brain startup."
        )
    return _components
