"""Prompt templates for KITTY brain service."""

from .expert_system import (
    REACT_INSTRUCTIONS,
    get_chain_of_thought_prompt,
    get_expert_system_prompt,
    get_react_agent_prompt,
)
from .tool_formatter import format_tools_compact, format_tools_for_prompt, get_tool_names

__all__ = [
    # Expert system prompts
    "get_expert_system_prompt",
    "get_chain_of_thought_prompt",
    "get_react_agent_prompt",
    "REACT_INSTRUCTIONS",
    # Tool formatters
    "format_tools_for_prompt",
    "format_tools_compact",
    "get_tool_names",
]
