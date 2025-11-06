# noqa: D401
"""HTTP client for llama.cpp server."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ..tools.parser import ToolCall, parse_tool_calls
from .config import LlamaCppConfig, get_routing_config


class LlamaCppClient:
    """Async wrapper around the llama.cpp HTTP server."""

    def __init__(self, config: Optional[LlamaCppConfig] = None) -> None:
        cfg = config or get_routing_config().llamacpp
        self._config = cfg
        self._base_url = cfg.host.rstrip("/")

    async def generate(
        self, prompt: str, model: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Invoke the completion endpoint and normalise the response.

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
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "n_predict": self._config.n_predict,
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "repeat_penalty": self._config.repeat_penalty,
            "stream": self._config.stream,
        }
        if self._config.stop_tokens:
            payload["stop"] = self._config.stop_tokens

        selected_model = model or self._config.model_alias
        if selected_model:
            payload["model"] = selected_model

        # Include tools if provided (requires llama-server with --jinja -fa flags)
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._config.timeout_seconds
        ) as client:
            response = await client.post(self._config.api_path, json=payload)
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

        completion = data.get("response") or data.get("content") or data.get("completion")
        if completion is None and "choices" in data:
            # OpenAI-compatible shape
            choices = data["choices"]
            if choices:
                completion = choices[0].get("message", {}).get("content")
        if completion is None and isinstance(data, dict):
            # fall back to joining chunks if present
            completion = data.get("generated_text") or ""

        # Parse tool calls from response (Qwen2.5 uses XML format)
        tool_calls: List[ToolCall] = []
        cleaned_text = completion or ""
        if tools and completion:
            tool_calls, cleaned_text = parse_tool_calls(completion)

        return {
            "response": cleaned_text,
            "tool_calls": tool_calls,
            "raw": data,
        }


__all__ = ["LlamaCppClient"]
