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
    "generate_cad_model": {
        "type": "function",
        "function": {
            "name": "generate_cad_model",
            "description": "Generate a 3D CAD model based on a text description. Use this when the user wants to design, model, or create a physical object or part.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed description of the object to design"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["step", "stl", "dxf"],
                        "description": "Output format for the CAD file"
                    }
                },
                "required": ["prompt"]
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
    "generate_cad_model": [
        "design", "model", "cad", "generate model",
        "create a design", "draw", "design me", "make a model",
        "3d print", "fabricate", "griffon", "griffin", "gryffon"
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

    selected: List[Dict[str, Any]] = []
    selected_names: set[str] = set()

    def _add_tool(name: str) -> None:
        if name in TOOL_DEFINITIONS and name not in selected_names:
            selected.append(TOOL_DEFINITIONS[name])
            selected_names.add(name)

    # Forced tools take precedence
    if forced_tools:
        for tool_name in forced_tools:
            _add_tool(tool_name)
        if selected:
            logger.info(f"Using forced tools: {sorted(selected_names)}")

    # Keyword-triggered tool (still allow additional auto tools)
    forced_tool = detect_forced_tool(prompt)
    if forced_tool:
        logger.info(f"Keyword-triggered tool detected: {forced_tool}")
        _add_tool(forced_tool)

    # Auto mode: heuristics determine additional tools
    if mode == "auto" and should_enable_tools_auto(prompt):
        logger.info("Auto-enabling full toolset based on prompt heuristics")
        for name in TOOL_DEFINITIONS:
            _add_tool(name)

    # Mode == "on": always include everything
    if mode == "on":
        logger.info("Tool mode 'on' - enabling all tools")
        for name in TOOL_DEFINITIONS:
            _add_tool(name)

    if selected:
        return selected

    logger.info("Tool detector returned no tools for this prompt")
    return []


def get_tools_for_prompt_semantic(
    prompt: str,
    all_tools: List[Dict[str, Any]],
    mode: str = "auto",
    top_k: int = 5,
    threshold: float = 0.3,
    forced_tools: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Semantic tool selection using embeddings.

    Falls back to keyword-based selection if embedding fails.

    Args:
        prompt: User's input prompt
        all_tools: List of all available tool definitions
        mode: "auto" (smart detection), "on" (always all), "off" (never)
        top_k: Maximum number of tools to return
        threshold: Minimum similarity score (0-1)
        forced_tools: Specific tool names to always include

    Returns:
        List of tool definitions in OpenAI format
    """
    if mode == "off":
        return []

    if mode == "on":
        logger.info("Tool mode 'on' - returning all tools")
        return all_tools

    # Import here to avoid circular imports and allow lazy loading
    try:
        from brain.tools.embeddings import get_embedding_manager
    except ImportError as e:
        logger.warning(f"Embeddings module not available: {e}, falling back to keyword-based")
        return get_tools_for_prompt(prompt, mode=mode, forced_tools=forced_tools)

    try:
        # Get embedding manager and ensure embeddings are computed
        manager = get_embedding_manager()
        manager.compute_embeddings(all_tools)

        # Search for relevant tools
        relevant_tools = manager.search(prompt, top_k=top_k, threshold=threshold)
        selected_names = {_get_tool_name(t) for t in relevant_tools}

        # Always include keyword-triggered tools
        forced_tool = detect_forced_tool(prompt)
        if forced_tool:
            logger.info(f"Adding keyword-triggered tool: {forced_tool}")
            for tool in all_tools:
                if _get_tool_name(tool) == forced_tool and forced_tool not in selected_names:
                    relevant_tools.append(tool)
                    selected_names.add(forced_tool)

        # Include explicitly forced tools
        if forced_tools:
            for tool_name in forced_tools:
                if tool_name not in selected_names:
                    for tool in all_tools:
                        if _get_tool_name(tool) == tool_name:
                            relevant_tools.append(tool)
                            selected_names.add(tool_name)
                            break

        logger.info(
            f"Semantic tool selection returned {len(relevant_tools)} tools: "
            f"{sorted(selected_names)}"
        )
        return relevant_tools

    except Exception as exc:
        logger.warning(f"Semantic tool selection failed: {exc}, falling back to keyword-based")
        return get_tools_for_prompt(prompt, mode=mode, forced_tools=forced_tools)


def _get_tool_name(tool: Dict[str, Any]) -> str:
    """Extract tool name from definition."""
    func = tool.get("function", tool)
    return func.get("name", "")


__all__ = [
    "TOOL_DEFINITIONS",
    "TOOL_KEYWORDS",
    "detect_forced_tool",
    "should_enable_tools_auto",
    "get_tools_for_prompt",
    "get_tools_for_prompt_semantic",
]
