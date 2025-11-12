# noqa: D401
"""HTTP client for llama.cpp server."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from ..tools.model_config import detect_model_format
from ..tools.parser import ToolCall, parse_tool_calls
from .config import LlamaCppConfig, get_routing_config

logger = logging.getLogger(__name__)


class LlamaCppClient:
    """Async wrapper around the llama.cpp HTTP server."""

    def __init__(self, config: Optional[LlamaCppConfig] = None) -> None:
        cfg = config or get_routing_config().llamacpp
        self._config = cfg
        self._base_url = cfg.host.rstrip("/")

        # Detect model format for tool calling (use alias or inferred local default)
        primary_fallback = getattr(cfg, "primary_model", None)
        model_identifier = cfg.model_alias or primary_fallback or os.getenv("LOCAL_MODEL_PRIMARY") or "qwen2.5"
        self._model_format = detect_model_format(model_identifier)
        logger.info(f"LlamaCppClient initialized with format: {self._model_format.value} (model: {model_identifier})")

    async def generate(
        self, prompt: str, model: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Invoke the OpenAI-compatible /v1/chat/completions endpoint.

        Args:
            prompt: The input prompt text
            model: Optional model alias to use (default from config)
            tools: Optional list of tool definitions in JSON Schema format

        Returns:
            Dict containing:
                - response: The text completion (str)
                - tool_calls: List of ToolCall objects if tools were invoked
                - raw: Raw API response
        """
        # Enforce temperature=0 for tool calling (hallucination prevention)
        temperature = self._config.temperature
        if tools:
            if temperature != 0:
                logger.warning(
                    f"Overriding temperature {temperature} -> 0 for tool calling "
                    "(deterministic output required for hallucination prevention)"
                )
            temperature = 0

        # Build OpenAI-compatible payload
        selected_model = model or self._config.model_alias or "default"

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self._config.n_predict,
            "temperature": temperature,
            "top_p": self._config.top_p,
            "stream": self._config.stream,
        }

        if self._config.stop_tokens:
            payload["stop"] = self._config.stop_tokens

        # Include tools if provided (OpenAI-compatible format)
        if tools:
            payload["tools"] = tools
            logger.info(f"Passing {len(tools)} tools to llama.cpp: {[t['function']['name'] for t in tools]}")

        # Log payload for debugging (truncate messages if too long)
        log_payload = payload.copy()
        if "messages" in log_payload and len(str(log_payload["messages"])) > 200:
            log_payload["messages"] = f"[{len(payload['messages'])} messages, {len(str(payload['messages']))} chars total]"
        logger.debug(f"llama.cpp OpenAI-compatible request: {log_payload}")

        # Use OpenAI-compatible endpoint
        endpoint = "/v1/chat/completions"

        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._config.timeout_seconds
        ) as client:
            try:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data: Dict[str, Any] = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"llama.cpp returned {e.response.status_code} from {endpoint}: {e.response.text[:500]}"
                )
                raise

        # Parse OpenAI-compatible response
        completion = None
        if "choices" in data and data["choices"]:
            choice = data["choices"][0]
            message = choice.get("message", {})
            completion = message.get("content", "")

        if completion is None:
            logger.warning(f"Unexpected response format from llama.cpp: {data}")
            completion = ""

        # Parse tool calls from response using detected model format
        tool_calls: List[ToolCall] = []
        cleaned_text = completion or ""
        if tools and completion:
            tool_calls, cleaned_text = parse_tool_calls(completion, format_type=self._model_format)
            if tool_calls:
                logger.info(f"Parsed {len(tool_calls)} tool calls from response: {[tc.name for tc in tool_calls]}")
            else:
                logger.warning("No tool calls found in model response despite tools being provided")

        # Extract metadata from OpenAI-compatible response
        stop_reason = None
        truncated = False
        if "choices" in data and data["choices"]:
            finish_reason = data["choices"][0].get("finish_reason")
            stop_reason = finish_reason
            truncated = (finish_reason == "length")

        return {
            "response": cleaned_text,
            "tool_calls": tool_calls,
            "raw": data,
            "stop_type": stop_reason,
            "truncated": truncated,
        }


__all__ = ["LlamaCppClient"]
