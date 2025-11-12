# noqa: D401
"""Simplified LLM client adapter for collective meta-agent integration.

This module provides a simple chat() interface that wraps KITTY's existing
Multi-server llama.cpp client infrastructure, allowing the collective meta-agent
to work with KITTY's Q4/F16 dual-model architecture.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Literal

from .routing.multi_server_client import MultiServerLlamaCppClient

logger = logging.getLogger(__name__)

# Global client instance (initialized lazily)
_client: MultiServerLlamaCppClient | None = None


def _get_client() -> MultiServerLlamaCppClient:
    """Get or create the global multi-server client instance."""
    global _client
    if _client is None:
        _client = MultiServerLlamaCppClient()
        logger.info("Initialized MultiServerLlamaCppClient for collective meta-agent")
    return _client


def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    """Convert OpenAI-style messages to a simple prompt string.

    Args:
        messages: List of message dicts with 'role' and 'content' keys

    Returns:
        Formatted prompt string
    """
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


async def chat_async(
    messages: List[Dict[str, str]],
    which: Literal["Q4", "F16", "CODER", "Q4B"] = "Q4",
    tools: List[Dict[str, Any]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None
) -> str:
    """Async chat interface for collective meta-agent.

    This is the preferred interface for use with async graph nodes.
    Provides clean async/await semantics without ThreadPoolExecutor workarounds.

    Args:
        messages: OpenAI-style message list [{"role": "user", "content": "..."}]
        which: Which model tier to use:
            - "Q4" for fast tool orchestrator (Qwen-based)
            - "F16" for deep reasoner (Llama-based)
            - "CODER" for code generation (Qwen-Coder)
            - "Q4B" for diversity seat (Mistral-based, falls back to Q4 if unavailable)
        tools: Optional tool definitions (JSON Schema format)
        temperature: Override default temperature (0.0-2.0)
        max_tokens: Override default max_tokens

    Returns:
        The assistant's text response

    Example:
        >>> response = await chat_async([
        ...     {"role": "system", "content": "You are a helpful assistant."},
        ...     {"role": "user", "content": "What is 2+2?"}
        ... ], which="Q4")
    """
    # Map which parameter to model alias
    # Q4B (diversity seat) falls back to Q4 if not configured
    model_map = {
        "Q4": "kitty-q4",
        "F16": "kitty-f16",
        "CODER": "kitty-coder",
        "Q4B": "kitty-q4b",  # Diversity seat (Mistral-7B or other model family)
    }
    model_alias = model_map.get(which, "kitty-q4")

    # Convert messages to prompt
    prompt = _messages_to_prompt(messages)

    # Get client and await async generation
    client = _get_client()
    result = await client.generate(prompt, model=model_alias, tools=tools)

    # Extract response text
    response_text = result.get("response", "")

    # Log tool calls if any
    tool_calls = result.get("tool_calls", [])
    if tool_calls:
        logger.info(f"Collective {which} generated {len(tool_calls)} tool calls: {[tc.name for tc in tool_calls]}")

    return response_text


def chat(
    messages: List[Dict[str, str]],
    which: Literal["Q4", "F16", "CODER", "Q4B"] = "Q4",
    tools: List[Dict[str, Any]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None
) -> str:
    """Synchronous chat interface for collective meta-agent.

    DEPRECATED: Use chat_async() instead for better performance.
    This sync wrapper uses ThreadPoolExecutor which adds overhead.

    This is a simplified wrapper around KITTY's async MultiServerLlamaCppClient
    that provides the interface expected by the collective module.

    Args:
        messages: OpenAI-style message list [{"role": "user", "content": "..."}]
        which: Which model tier to use:
            - "Q4" for fast tool orchestrator (Qwen-based)
            - "F16" for deep reasoner (Llama-based)
            - "CODER" for code generation (Qwen-Coder)
            - "Q4B" for diversity seat (Mistral-based, falls back to Q4 if unavailable)
        tools: Optional tool definitions (JSON Schema format)
        temperature: Override default temperature (0.0-2.0)
        max_tokens: Override default max_tokens

    Returns:
        The assistant's text response

    Example:
        >>> response = chat([
        ...     {"role": "system", "content": "You are a helpful assistant."},
        ...     {"role": "user", "content": "What is 2+2?"}
        ... ], which="Q4")
    """
    # Map which parameter to model alias
    # Q4B (diversity seat) falls back to Q4 if not configured
    model_map = {
        "Q4": "kitty-q4",
        "F16": "kitty-f16",
        "CODER": "kitty-coder",
        "Q4B": "kitty-q4b",  # Diversity seat (Mistral-7B or other model family)
    }
    model_alias = model_map.get(which, "kitty-q4")

    # Convert messages to prompt
    prompt = _messages_to_prompt(messages)

    # Get client and run async generation in sync context
    client = _get_client()

    try:
        # Run async call in event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, we need to create a new loop
            # This is a workaround for sync/async mixing
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    lambda: asyncio.run(client.generate(prompt, model=model_alias, tools=tools))
                ).result()
        else:
            # Safe to run in current loop
            result = loop.run_until_complete(client.generate(prompt, model=model_alias, tools=tools))
    except RuntimeError:
        # If no event loop exists, create one
        result = asyncio.run(client.generate(prompt, model=model_alias, tools=tools))

    # Extract response text
    response_text = result.get("response", "")

    # Log tool calls if any
    tool_calls = result.get("tool_calls", [])
    if tool_calls:
        logger.info(f"Collective {which} generated {len(tool_calls)} tool calls: {[tc.name for tc in tool_calls]}")

    return response_text


__all__ = ["chat", "chat_async"]
