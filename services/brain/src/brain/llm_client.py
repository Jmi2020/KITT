# noqa: D401
"""Unified LLM client supporting local and cloud providers.

This module provides a simple chat() interface that wraps KITTY's existing
Multi-server llama.cpp client infrastructure, allowing the collective meta-agent
to work with both local (Q4/F16/CODER) and cloud providers (OpenAI, Anthropic, etc.).

Cloud providers are disabled by default and require feature flags to enable.
When disabled, requests automatically fall back to local Q4.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Literal, Optional, Tuple

from .routing.multi_server_client import MultiServerLlamaCppClient

logger = logging.getLogger(__name__)

# Provider feature flags (from I/O Control or environment)
ENABLE_OPENAI_COLLECTIVE = os.getenv("ENABLE_OPENAI_COLLECTIVE", "false").lower() == "true"
ENABLE_ANTHROPIC_COLLECTIVE = os.getenv("ENABLE_ANTHROPIC_COLLECTIVE", "false").lower() == "true"
ENABLE_MISTRAL_COLLECTIVE = os.getenv("ENABLE_MISTRAL_COLLECTIVE", "false").lower() == "true"
ENABLE_PERPLEXITY_COLLECTIVE = os.getenv("ENABLE_PERPLEXITY_COLLECTIVE", "false").lower() == "true"
ENABLE_GEMINI_COLLECTIVE = os.getenv("ENABLE_GEMINI_COLLECTIVE", "false").lower() == "true"

# Cost tracking per provider (USD per 1M tokens)
PROVIDER_COSTS = {
    "openai": {"input": 0.15, "output": 0.60},      # gpt-4o-mini
    "anthropic": {"input": 0.25, "output": 1.25},   # claude-3-5-haiku
    "mistral": {"input": 0.10, "output": 0.30},     # mistral-small
    "perplexity": {"input": 0.20, "output": 0.20},  # sonar
    "gemini": {"input": 0.075, "output": 0.30},     # gemini-1.5-flash
}

# Global client instances (initialized lazily)
_local_client: MultiServerLlamaCppClient | None = None
_provider_registry: Optional["ProviderRegistry"] = None


class ProviderRegistry:
    """Lazy-loading registry for cloud LLM providers.

    Providers are only initialized when first requested AND enabled via feature flags.
    This ensures zero overhead when cloud providers are disabled (default).
    """

    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._initialized: Dict[str, bool] = {}
        logger.debug("Initialized ProviderRegistry")

    def is_enabled(self, provider: str) -> bool:
        """Check if provider is enabled via feature flags.

        Args:
            provider: Provider name (e.g., "openai", "anthropic")

        Returns:
            True if provider is enabled, False otherwise
        """
        flags = {
            "openai": ENABLE_OPENAI_COLLECTIVE,
            "anthropic": ENABLE_ANTHROPIC_COLLECTIVE,
            "mistral": ENABLE_MISTRAL_COLLECTIVE,
            "perplexity": ENABLE_PERPLEXITY_COLLECTIVE,
            "gemini": ENABLE_GEMINI_COLLECTIVE,
        }
        return flags.get(provider, False)

    def get_provider(self, provider: str) -> Optional[Any]:
        """Get or initialize provider client (lazy).

        Args:
            provider: Provider name (e.g., "openai", "anthropic")

        Returns:
            Provider client instance if enabled, None otherwise
        """
        if provider in ["Q4", "F16", "CODER", "Q4B"]:
            # Local providers always available, handled by MultiServerLlamaCppClient
            return None

        if not self.is_enabled(provider):
            logger.debug(f"Provider '{provider}' is disabled, will fallback to Q4")
            return None

        # Lazy initialization
        if provider not in self._initialized:
            try:
                self._init_provider(provider)
                self._initialized[provider] = True
                logger.info(f"Initialized provider '{provider}' for collective meta-agent")
            except ImportError as e:
                logger.warning(
                    f"Failed to initialize provider '{provider}': {e}. "
                    f"Install with: pip install any-llm-sdk[{provider}]"
                )
                return None
            except Exception as e:
                logger.error(f"Error initializing provider '{provider}': {e}")
                return None

        return self._providers.get(provider)

    def _init_provider(self, provider: str) -> None:
        """Initialize cloud provider using any-llm SDK.

        Args:
            provider: Provider name (e.g., "openai", "anthropic")
        """
        try:
            from any_llm import AnyLLM
        except ImportError:
            logger.error(
                "any-llm-sdk not installed. Install with: pip install any-llm-sdk"
            )
            raise

        # Get API key from environment
        api_key_map = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "mistral": os.getenv("MISTRAL_API_KEY"),
            "perplexity": os.getenv("PERPLEXITY_API_KEY"),
            "gemini": os.getenv("GEMINI_API_KEY"),
        }

        api_key = api_key_map.get(provider)
        if not api_key:
            raise ValueError(
                f"No API key found for provider '{provider}'. "
                f"Set {provider.upper()}_API_KEY in environment."
            )

        # Create provider instance (with connection pooling!)
        self._providers[provider] = AnyLLM.create(
            provider=provider,
            api_key=api_key,
        )


def _get_local_client() -> MultiServerLlamaCppClient:
    """Get or create the global local llama.cpp client instance."""
    global _local_client
    if _local_client is None:
        _local_client = MultiServerLlamaCppClient()
        logger.info("Initialized MultiServerLlamaCppClient for collective meta-agent")
    return _local_client


def _get_provider_registry() -> ProviderRegistry:
    """Get or create the global provider registry instance."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry


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
    model: Optional[str] = None,
    provider: Optional[str] = None,
    tools: List[Dict[str, Any]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    fallback_to_local: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Unified async chat interface supporting local and cloud providers.

    **Local-first behavior (default):**
    ```python
    # Uses local llama.cpp (unchanged from current)
    response, metadata = await chat_async(
        messages=[...],
        which="Q4"
    )
    ```

    **Multi-provider support (new):**
    ```python
    # Uses GPT-4 if ENABLE_OPENAI_COLLECTIVE=true, else falls back to Q4
    response, metadata = await chat_async(
        messages=[...],
        model="gpt-4o-mini",
        provider="openai"
    )
    ```

    Args:
        messages: OpenAI-style message list [{"role": "user", "content": "..."}]
        which: Local model tier (Q4/F16/CODER/Q4B) - used for local or fallback
        model: Cloud model name (e.g., "gpt-4o-mini", "claude-3-5-haiku-20241022")
        provider: Cloud provider name (e.g., "openai", "anthropic")
        tools: Optional tool definitions (JSON Schema format)
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Max tokens to generate
        fallback_to_local: If True, fall back to local `which` if cloud provider disabled

    Returns:
        Tuple of (response_text, metadata_dict) where metadata contains:
        - provider_used: Which provider was used (e.g., "openai", "local")
        - model_used: Which model was used (e.g., "gpt-4o-mini", "kitty-q4")
        - fallback_occurred: Whether fallback to local happened
        - tokens_used: Token count (if available)
        - cost_usd: Estimated cost (if cloud provider)

    Example:
        >>> # Local (backward compatible)
        >>> response, meta = await chat_async([{"role": "user", "content": "Hi"}], which="Q4")
        >>> print(meta["provider_used"])  # "local"

        >>> # Cloud with fallback
        >>> response, meta = await chat_async(
        ...     [{"role": "user", "content": "Hi"}],
        ...     model="gpt-4o-mini",
        ...     provider="openai"
        ... )
        >>> print(meta["provider_used"])  # "openai" or "local" (if disabled)
    """
    metadata: Dict[str, Any] = {
        "provider_used": "local",
        "model_used": None,
        "fallback_occurred": False,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }

    # Determine routing: cloud or local
    if provider and model:
        # Attempt cloud provider
        registry = _get_provider_registry()
        cloud_provider = registry.get_provider(provider)

        if cloud_provider:
            try:
                # Use any-llm SDK
                from any_llm import acompletion

                result = await acompletion(
                    model=model,
                    provider=provider,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )

                # Extract text content
                if hasattr(result, "choices") and result.choices:
                    response_text = result.choices[0].message.content

                    # Update metadata
                    metadata["provider_used"] = provider
                    metadata["model_used"] = model
                    metadata["fallback_occurred"] = False

                    # Extract token usage if available
                    if hasattr(result, "usage"):
                        input_tokens = getattr(result.usage, "prompt_tokens", 0)
                        output_tokens = getattr(result.usage, "completion_tokens", 0)
                        metadata["tokens_used"] = input_tokens + output_tokens

                        # Estimate cost
                        if provider in PROVIDER_COSTS:
                            costs = PROVIDER_COSTS[provider]
                            cost = (
                                (input_tokens / 1_000_000) * costs["input"] +
                                (output_tokens / 1_000_000) * costs["output"]
                            )
                            metadata["cost_usd"] = cost

                    logger.info(
                        f"Collective used cloud provider: {provider}/{model} "
                        f"({len(response_text)} chars, {metadata['tokens_used']} tokens, "
                        f"${metadata['cost_usd']:.6f})"
                    )
                    return response_text, metadata

            except Exception as exc:
                logger.warning(
                    f"Cloud provider '{provider}' failed: {exc}. "
                    f"Falling back to local {which}"
                )
                metadata["fallback_occurred"] = True

        else:
            # Provider not available or disabled
            if fallback_to_local:
                logger.info(
                    f"Cloud provider '{provider}' unavailable or disabled. "
                    f"Using local {which}"
                )
                metadata["fallback_occurred"] = True
            else:
                raise RuntimeError(
                    f"Cloud provider '{provider}' unavailable and fallback disabled"
                )

    # Use local llama.cpp (existing behavior)
    model_map = {
        "Q4": "kitty-q4",
        "F16": "kitty-f16",
        "CODER": "kitty-coder",
        "Q4B": "kitty-q4b",
    }
    model_alias = model_map.get(which, "kitty-q4")

    # Convert messages to prompt
    prompt = _messages_to_prompt(messages)

    # Get local client
    client = _get_local_client()
    result = await client.generate(prompt, model=model_alias, tools=tools)

    # Extract response text
    response_text = result.get("response", "")

    # Update metadata for local
    metadata["provider_used"] = "local"
    metadata["model_used"] = model_alias
    metadata["tokens_used"] = 0  # Local doesn't track tokens
    metadata["cost_usd"] = 0.0  # Local is free

    # Log tool calls if any and include in metadata
    tool_calls = result.get("tool_calls", [])
    if tool_calls:
        logger.info(
            f"Collective {which} generated {len(tool_calls)} tool calls: "
            f"{[tc.get('function', {}).get('name') if isinstance(tc, dict) else getattr(tc, 'name', 'unknown') for tc in tool_calls]}"
        )
    metadata["tool_calls"] = tool_calls

    return response_text, metadata


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


__all__ = ["chat", "chat_async", "ProviderRegistry", "PROVIDER_COSTS"]
