"""
Research Tools Integration

Integrates MCP tools (web_search, Perplexity, memory) with the autonomous research pipeline.
Uses UnifiedPermissionGate for streamlined permission checks.
"""

from .mcp_integration import (
    ResearchToolExecutor,
    ToolExecutionContext,
    ToolExecutionResult,
)
from .safety import (
    ResearchPermissionManager,  # DEPRECATED: Use UnifiedPermissionGate
    ToolSafetyChecker,  # DEPRECATED: Integrated into UnifiedPermissionGate
)

__all__ = [
    "ResearchToolExecutor",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ResearchPermissionManager",  # DEPRECATED
    "ToolSafetyChecker",  # DEPRECATED
]
