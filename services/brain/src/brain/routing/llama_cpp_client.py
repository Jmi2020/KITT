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
        openai_tool_calls = None
        if "choices" in data and data["choices"]:
            choice = data["choices"][0]
            message = choice.get("message", {})
            completion = message.get("content", "")
            # Check for OpenAI-format tool_calls in the message
            openai_tool_calls = message.get("tool_calls")

        if completion is None:
            logger.debug(f"No text content in response (tool_calls may be present): {data}")
            completion = ""

        # Parse tool calls from response
        tool_calls: List[ToolCall] = []
        cleaned_text = completion or ""

        # First, check for OpenAI-format tool_calls in the response
        if tools and openai_tool_calls:
            import json as json_module
            for tc in openai_tool_calls:
                if isinstance(tc, dict) and tc.get("type") == "function":
                    func = tc.get("function", {})
                    name = func.get("name")
                    args = func.get("arguments", {})
                    # Arguments may be a JSON string, parse if needed
                    if isinstance(args, str):
                        try:
                            args = json_module.loads(args)
                        except json_module.JSONDecodeError:
                            args = {}
                    if name:
                        # raw_xml represents the original format, use JSON representation for OpenAI format
                        raw_repr = json_module.dumps(tc)
                        tool_calls.append(ToolCall(name=name, arguments=args, raw_xml=raw_repr))
            if tool_calls:
                logger.info(f"Extracted {len(tool_calls)} tool calls from OpenAI format: {[tc.name for tc in tool_calls]}")

        # Fall back to parsing from text content if no OpenAI-format tool_calls
        if tools and not tool_calls and completion:
            tool_calls, cleaned_text = parse_tool_calls(completion, format_type=self._model_format)
            if tool_calls:
                logger.info(f"Parsed {len(tool_calls)} tool calls from text: {[tc.name for tc in tool_calls]}")

        if tools and not tool_calls:
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
