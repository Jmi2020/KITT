# noqa: D401
"""Tool registry and smart detection for automatic tool calling."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Tool definitions in OpenAI/llama.cpp format
TOOL_DEFINITIONS = {
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, facts, prices, or any real-time data. Use this when the user asks about current events, latest information, or anything that requires up-to-date knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to execute"
                    }
                },
                "required": ["query"]
            }
        }
    },
    "generate_cad": {
        "type": "function",
        "function": {
            "name": "generate_cad",
            "description": "Generate a 3D CAD model based on a text description. Use this when the user wants to design, model, or create a physical object or part.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the object to design"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["step", "stl", "dxf"],
                        "description": "Output format for the CAD file"
                    }
                },
                "required": ["description"]
            }
        }
    },
    "reason_with_f16": {
        "type": "function",
        "function": {
            "name": "reason_with_f16",
            "description": "Delegate to the F16 reasoning engine for comprehensive, nuanced analysis. Use this for complex questions requiring deep thinking, multi-step reasoning, or detailed explanations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The complex question or reasoning task to delegate to the F16 model"
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context from tool results or previous steps"
                    }
                },
                "required": ["query"]
            }
        }
    },
}


# Keywords that explicitly trigger specific tools
TOOL_KEYWORDS = {
    "web_search": [
        "search for", "look up", "find", "research",
        "google", "what is the latest", "current", "today",
        "recent", "news about", "price of", "cost of"
    ],
    "generate_cad": [
        "design", "model", "cad", "generate model",
        "create a design", "draw", "design me", "make a model"
    ],
    "reason_with_f16": [
        "explain in detail", "analyze", "deep dive", "comprehensive",
        "thorough explanation", "detailed analysis", "think through"
    ],
}


def detect_forced_tool(prompt: str) -> Optional[str]:
    """Check if user explicitly requested a specific tool via keywords.

    Args:
        prompt: User's input prompt

    Returns:
        Tool name if explicitly requested, None otherwise
    """
    prompt_lower = prompt.lower()

    for tool, keywords in TOOL_KEYWORDS.items():
        if any(keyword in prompt_lower for keyword in keywords):
            logger.info(f"Keyword triggered tool: {tool}")
            return tool

    return None


def should_enable_tools_auto(prompt: str) -> bool:
    """Heuristic to determine if tools should be automatically enabled.

    Detects questions, requests for current data, or fabrication needs.

    Args:
        prompt: User's input prompt

    Returns:
        True if tools should be enabled
    """
    prompt_lower = prompt.lower()

    # Current/real-time data indicators
    realtime_indicators = [
        "current", "latest", "today", "now", "recent",
        "price", "stock", "weather", "news", "2024", "2025"
    ]
    if any(word in prompt_lower for word in realtime_indicators):
        logger.info("Auto-enabling tools: real-time data detected")
        return True

    # Question indicators
    question_starters = [
        "what is", "what's", "how much", "when did",
        "where is", "who is", "how many", "how does"
    ]
    if any(prompt_lower.startswith(q) for q in question_starters):
        logger.info("Auto-enabling tools: question detected")
        return True

    # Question words anywhere in prompt
    if any(word in prompt_lower for word in ["what", "how", "when", "where", "who", "why"]):
        if "?" in prompt:  # Has question mark
            logger.info("Auto-enabling tools: question format detected")
            return True

    # Fabrication/design requests
    fabrication_indicators = [
        "design", "model", "cad", "generate", "create a",
        "make a", "build a", "fabricate"
    ]
    if any(word in prompt_lower for word in fabrication_indicators):
        logger.info("Auto-enabling tools: fabrication request detected")
        return True

    return False


def get_tools_for_prompt(
    prompt: str,
    mode: str = "auto",
    forced_tools: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Get tool definitions to pass to the model.

    Args:
        prompt: User's input prompt
        mode: "auto" (smart detection), "on" (always), "off" (never)
        forced_tools: Specific tool names to enable (overrides mode)

    Returns:
        List of tool definitions in OpenAI format
    """
    if mode == "off":
        return []

    # Check for forced tools first
    if forced_tools:
        tools = []
        for tool_name in forced_tools:
            if tool_name in TOOL_DEFINITIONS:
                tools.append(TOOL_DEFINITIONS[tool_name])
        if tools:
            logger.info(f"Using forced tools: {forced_tools}")
            return tools

    # Check for explicit keywords
    forced_tool = detect_forced_tool(prompt)
    if forced_tool and forced_tool in TOOL_DEFINITIONS:
        logger.info(f"Using keyword-triggered tool: {forced_tool}")
        return [TOOL_DEFINITIONS[forced_tool]]

    # Auto mode: smart detection
    if mode == "auto":
        if should_enable_tools_auto(prompt):
            # Enable all tools for now (can be refined later)
            logger.info("Auto-enabling all available tools")
            return list(TOOL_DEFINITIONS.values())
        else:
            logger.info("No tools needed for this prompt")
            return []

    # Mode == "on": always enable all tools
    if mode == "on":
        logger.info("Tools forced on: enabling all tools")
        return list(TOOL_DEFINITIONS.values())

    return []


__all__ = [
    "TOOL_DEFINITIONS",
    "TOOL_KEYWORDS",
    "detect_forced_tool",
    "should_enable_tools_auto",
    "get_tools_for_prompt",
]
