"""
Research Tools Integration

Integrates MCP tools (web_search, Perplexity, memory) with the autonomous research pipeline.
Provides safety checks via I/O control and permission manager.
"""

from .mcp_integration import (
    ResearchToolExecutor,
    ToolExecutionContext,
    ToolExecutionResult,
)
from .safety import (
    ResearchPermissionManager,
    ToolSafetyChecker,
)

__all__ = [
    "ResearchToolExecutor",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ResearchPermissionManager",
    "ToolSafetyChecker",
]
