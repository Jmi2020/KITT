# noqa: D401
"""HTTP client for llama.cpp server."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import LlamaCppConfig, get_routing_config


class LlamaCppClient:
    """Async wrapper around the llama.cpp HTTP server."""

    def __init__(self, config: Optional[LlamaCppConfig] = None) -> None:
        cfg = config or get_routing_config().llamacpp
        self._config = cfg
        self._base_url = cfg.host.rstrip("/")

    async def generate(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Invoke the completion endpoint and normalise the response."""

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

        return {
            "response": completion or "",
            "raw": data,
        }


__all__ = ["LlamaCppClient"]
