"""Shared types for agent workflows.

This module contains data structures used across the agent system to avoid
circular imports between conversation state management and agent execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AgentStep:
    """A single step in the ReAct loop."""

    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    is_final: bool = False


@dataclass
class AgentResult:
    """Final result from agent execution."""

    answer: str
    steps: List[AgentStep]
    success: bool
    error: Optional[str] = None
    iterations: int = 0
    truncated: bool = False
    stop_reason: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_phrase: Optional[str] = None
    pending_tool: Optional[str] = None
    pending_tool_args: Optional[Dict[str, Any]] = None
    hazard_class: Optional[str] = None


__all__ = ["AgentStep", "AgentResult"]
