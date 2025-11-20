# SPDX-License-Identifier: MIT
"""
Ollama client for GPT-OSS 120B with thinking mode support.

Provides a minimal HTTP client for the Ollama chat API with support for:
- Thinking mode parameter (low/medium/high for GPT-OSS)
- Streaming and non-streaming responses
- Thinking trace capture for telemetry (separate from user content)
"""
from __future__ import annotations

import httpx
import json
import logging
from typing import Iterable, Optional, Dict, Any, Generator

logger = logging.getLogger(__name__)


class OllamaReasonerClient:
    """
    HTTP client for Ollama chat API with GPT-OSS thinking mode support.

    The client handles both streaming and non-streaming requests, capturing
    the optional 'thinking' trace separately from the response content.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: int = 120,
        keep_alive: str = "5m"
    ):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server URL (e.g., http://localhost:11434)
            model: Model name (e.g., gpt-oss:120b)
            timeout_s: Request timeout in seconds
            keep_alive: Model keep-alive duration (e.g., "5m", "10m")
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_s
        self.keep_alive = keep_alive

        logger.info(
            f"Initialized OllamaReasonerClient: model={model}, "
            f"base_url={base_url}, timeout={timeout_s}s"
        )

    def _make_payload(
        self,
        messages: Iterable[Dict[str, str]],
        think: Optional[str] = None,
        stream: bool = True
    ) -> Dict[str, Any]:
        """
        Build Ollama chat API request payload.

        Args:
            messages: Chat messages in OpenAI format
            think: Thinking effort level (low|medium|high) for GPT-OSS
            stream: Enable streaming mode

        Returns:
            Request payload dictionary
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": stream,
            "keep_alive": self.keep_alive,
        }

        # GPT-OSS expects "low|medium|high" string values
        # Other Ollama models may support true/false
        if think is not None:
            payload["think"] = think
            logger.debug(f"Thinking mode enabled: {think}")

        return payload

    def chat(
        self,
        messages: Iterable[Dict[str, str]],
        think: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Non-streaming chat completion.

        Args:
            messages: Chat messages in OpenAI format
            think: Thinking effort level (low|medium|high)
            stream: Must be False for this method

        Returns:
            Dictionary with:
                - content: Response text
                - role: Assistant role
                - thinking: Optional thinking trace (if enabled)
                - raw: Full API response
        """
        logger.debug(f"Sending non-streaming request to {self.base_url}/api/chat")

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/api/chat",
                json=self._make_payload(messages, think, stream=False)
            )
            resp.raise_for_status()
            data = resp.json()

        # Normalize shape across Ollama API versions
        msg = data.get("message", {})
        thinking = msg.get("thinking") or data.get("thinking")

        if thinking:
            logger.info(f"Thinking trace captured ({len(thinking)} chars)")

        return {
            "content": msg.get("content", ""),
            "role": msg.get("role", "assistant"),
            "thinking": thinking,
            "raw": data,
        }

    def stream_chat(
        self,
        messages: Iterable[Dict[str, str]],
        think: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming chat completion.

        Yields incremental deltas for both content and thinking traces.
        Consumer should buffer 'delta' field and optionally log 'delta_thinking'.

        Args:
            messages: Chat messages in OpenAI format
            think: Thinking effort level (low|medium|high)

        Yields:
            Dictionary with:
                - delta: Content delta
                - delta_thinking: Thinking trace delta (optional)
                - done: True on final chunk
        """
        logger.debug(f"Starting streaming request to {self.base_url}/api/chat")

        with httpx.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=self._make_payload(messages, think, stream=True),
            timeout=self.timeout
        ) as r:
            r.raise_for_status()

            for line in r.iter_lines():
                if not line:
                    continue

                # Handle both NDJSON and SSE "data: {json}" formats
                if line.startswith("data:"):
                    line = line[5:].strip()

                try:
                    chunk = json.loads(line)
                except Exception as e:
                    logger.warning(f"Failed to parse streaming chunk: {e}")
                    continue

                msg = chunk.get("message", {})
                yield {
                    "delta": msg.get("content", ""),
                    "delta_thinking": msg.get("thinking"),
                    "done": chunk.get("done", False),
                }

    def health_check(self) -> bool:
        """
        Check if Ollama server is healthy and model is available.

        Returns:
            True if server is healthy and model exists
        """
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()

                # Check if our model is in the list
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]

                if self.model in model_names:
                    logger.info(f"Health check OK: {self.model} is available")
                    return True
                else:
                    logger.warning(
                        f"Health check warning: {self.model} not found. "
                        f"Available: {model_names}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
