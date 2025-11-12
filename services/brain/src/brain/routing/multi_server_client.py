# noqa: D401
"""Multi-server llama.cpp client for dual-model architecture."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .config import LlamaCppConfig


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
from .llama_cpp_client import LlamaCppClient

logger = logging.getLogger(__name__)


class MultiServerLlamaCppClient:
    """Routes llama.cpp requests to different servers based on model alias.

    Supports Q4 (tool orchestrator) and F16 (reasoning engine) on separate ports.
    """

    def __init__(self) -> None:
        """Initialize clients for Q4 and F16 models."""
        self._clients: Dict[str, LlamaCppClient] = {}

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
        """Route generation request to appropriate llama-server.

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
        return await client.generate(prompt, model=selected_model, tools=tools)


__all__ = ["MultiServerLlamaCppClient"]
