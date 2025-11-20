# noqa: D401
"""Multi-server llama.cpp client for dual-model architecture with Ollama support."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .config import LlamaCppConfig, OllamaConfig, get_routing_config
from .llama_cpp_client import LlamaCppClient
from .ollama_client import OllamaReasonerClient

logger = logging.getLogger(__name__)


def _resolve_timeout(*env_vars: str) -> float:
    """Get timeout seconds from env-specific overrides with sane defaults."""

    default_timeout = LlamaCppConfig().timeout_seconds

    for env_var in env_vars:
        if not env_var:
            continue
        value = os.getenv(env_var)
        if value:
            try:
                return float(value)
            except ValueError:
                logger.warning(
                    "Invalid %s value '%s'; falling back to %.1fs",
                    env_var,
                    value,
                    default_timeout,
                )

    return default_timeout


class MultiServerLlamaCppClient:
    """Routes requests to different LLM servers based on model alias.

    Supports:
    - Q4 (tool orchestrator) on llama.cpp
    - F16 (reasoning engine) on llama.cpp OR Ollama (configurable)
    - Ollama GPT-OSS 120B with thinking mode
    """

    def __init__(self) -> None:
        """Initialize clients for Q4, F16, and optionally Ollama models."""
        self._clients: Dict[str, Any] = {}  # Can hold LlamaCppClient or OllamaReasonerClient
        self._ollama_client: Optional[OllamaReasonerClient] = None

        # Q4 Model Configuration (Tool Orchestrator - Port 8083)
        q4_host = os.getenv("LLAMACPP_Q4_HOST", "http://localhost:8083")
        q4_alias = os.getenv("LLAMACPP_Q4_ALIAS", "kitty-q4")
        q4_timeout = _resolve_timeout("LLAMACPP_Q4_TIMEOUT", "LLAMACPP_TIMEOUT")
        q4_config = LlamaCppConfig(
            host=q4_host,
            model_alias=q4_alias,
            temperature=float(os.getenv("LLAMACPP_Q4_TEMPERATURE", "0.1")),
            timeout_seconds=q4_timeout,
        )
        self._clients[q4_alias] = LlamaCppClient(config=q4_config)
        logger.info(f"Registered Q4 client: {q4_alias} @ {q4_host}")

        # Get router configuration
        routing_config = get_routing_config()
        local_reasoner_provider = routing_config.local_reasoner_provider

        if local_reasoner_provider == "ollama":
            # Ollama Reasoner Configuration (GPT-OSS 120B with Thinking)
            ollama_cfg = routing_config.ollama
            self._ollama_client = OllamaReasonerClient(
                base_url=ollama_cfg.host,
                model=ollama_cfg.model,
                timeout_s=int(ollama_cfg.timeout_seconds),
                keep_alive=ollama_cfg.keep_alive,
            )
            # Register Ollama as the F16 reasoner
            f16_alias = os.getenv("LLAMACPP_F16_ALIAS", "kitty-f16")
            self._clients[f16_alias] = "ollama"  # Marker for Ollama routing
            logger.info(
                f"Registered Ollama reasoner: {f16_alias} @ {ollama_cfg.host} "
                f"(model={ollama_cfg.model}, think={ollama_cfg.think})"
            )
        else:
            # F16 Model Configuration (Reasoning Engine - Port 8082)
            f16_host = os.getenv("LLAMACPP_F16_HOST", "http://localhost:8082")
            f16_alias = os.getenv("LLAMACPP_F16_ALIAS", "kitty-f16")
            f16_timeout = _resolve_timeout("LLAMACPP_F16_TIMEOUT", "LLAMACPP_TIMEOUT")
            f16_config = LlamaCppConfig(
                host=f16_host,
                model_alias=f16_alias,
                temperature=float(os.getenv("LLAMACPP_F16_TEMPERATURE", "0.2")),
                timeout_seconds=f16_timeout,
            )
            self._clients[f16_alias] = LlamaCppClient(config=f16_config)
            logger.info(f"Registered F16 client: {f16_alias} @ {f16_host}")

        # Set default orchestrator model
        self._default_model = q4_alias

    async def generate(
        self, prompt: str, model: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Route generation request to appropriate LLM server (llama.cpp or Ollama).

        Args:
            prompt: The input prompt text
            model: Model alias (e.g., "kitty-q4", "kitty-f16")
            tools: Optional tool definitions

        Returns:
            Dict containing response, tool_calls, and metadata

        Raises:
            ValueError: If model alias is unknown
        """
        selected_model = model or self._default_model

        client = self._clients.get(selected_model)
        if not client:
            raise ValueError(
                f"Unknown model '{selected_model}'. Available: {list(self._clients.keys())}"
            )

        logger.debug(f"Routing to {selected_model}")

        # Handle Ollama routing
        if client == "ollama" and self._ollama_client:
            return await self._generate_ollama(prompt, tools)

        # Handle llama.cpp routing
        return await client.generate(prompt, model=selected_model, tools=tools)

    async def _generate_ollama(
        self, prompt: str, tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate response using Ollama with thinking mode and tool calling.

        Adapts Ollama's response format to match llama.cpp client expectations.

        Args:
            prompt: The input prompt text
            tools: Optional tool definitions (OpenAI format)

        Returns:
            Dict with keys: response, thinking (optional), tool_calls, metadata
        """
        # Get thinking level from config
        routing_config = get_routing_config()
        think_level = routing_config.ollama.think

        # Build messages in OpenAI format
        messages = [{"role": "user", "content": prompt}]

        # Call Ollama with tools and thinking mode
        logger.debug(
            f"Calling Ollama with thinking mode: {think_level}, "
            f"tools: {len(tools) if tools else 0}"
        )
        result = self._ollama_client.chat(
            messages, think=think_level, stream=False, tools=tools
        )

        # Log thinking trace if present (but don't include in user response)
        if result.get("thinking"):
            thinking_len = len(result["thinking"])
            logger.info(f"Ollama thinking trace captured ({thinking_len} chars)")
            # TODO: Store to reasoning.jsonl for telemetry

        # Normalize to llama.cpp response format
        return {
            "response": result["content"],
            "thinking": result.get("thinking"),
            "tool_calls": result.get("tool_calls", []),
            "provider": "ollama",
            "model": routing_config.ollama.model,
        }

    async def generate_stream(
        self, prompt: str, model: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None
    ):
        """Stream generation request with real-time thinking traces and optional tool calling.

        Yields chunks in format:
        {
            "delta": str,              # Content delta
            "delta_thinking": str,     # Thinking trace delta (optional)
            "tool_calls": List,        # Tool calls (typically in final chunk)
            "done": bool,              # Whether stream is complete
        }

        Note: Currently only supports Ollama models with thinking mode.
        llama.cpp streaming support to be added in future.

        Args:
            prompt: The input prompt text
            model: Model alias (e.g., "kitty-f16" for Ollama reasoner)
            tools: Optional tool definitions (OpenAI format)

        Yields:
            Dict containing delta, delta_thinking, tool_calls, and done flag

        Raises:
            ValueError: If model alias is unknown
            NotImplementedError: If model doesn't support streaming
        """
        selected_model = model or self._default_model

        client = self._clients.get(selected_model)
        if not client:
            raise ValueError(
                f"Unknown model '{selected_model}'. Available: {list(self._clients.keys())}"
            )

        logger.debug(f"Streaming from {selected_model}")

        # Handle Ollama streaming
        if client == "ollama" and self._ollama_client:
            # Get thinking level from config
            routing_config = get_routing_config()
            think_level = routing_config.ollama.think

            # Build messages in OpenAI format
            messages = [{"role": "user", "content": prompt}]

            logger.debug(
                f"Streaming from Ollama with thinking mode: {think_level}, "
                f"tools: {len(tools) if tools else 0}"
            )

            # Stream from Ollama with tools
            for chunk in self._ollama_client.stream_chat(messages, think=think_level, tools=tools):
                yield chunk
            return

        # llama.cpp streaming not yet implemented
        raise NotImplementedError(
            f"Streaming not yet supported for llama.cpp models (requested: {selected_model}). "
            "Use Ollama reasoner (LOCAL_REASONER_PROVIDER=ollama) for streaming with thinking traces."
        )


__all__ = ["MultiServerLlamaCppClient"]
