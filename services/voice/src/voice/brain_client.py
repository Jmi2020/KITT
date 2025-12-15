"""HTTP client for Brain API.

This module provides an async HTTP client for the Brain service,
replacing direct orchestrator imports. Using HTTP ensures:
1. Proper SlotManager lifecycle (auto-restart of idle LLM servers)
2. Clean separation between voice and brain services
3. Consistent routing behavior across all clients
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

# Brain service URL (Docker internal or localhost for development)
BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://localhost:8000")


@dataclass
class BrainResponse:
    """Response from Brain API /query endpoint."""

    output: str
    tier: str
    confidence: float = 0.0
    latency_ms: int = 0
    cached: bool = False
    metadata: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False
    confirmation_phrase: Optional[str] = None
    pending_tool: Optional[str] = None
    hazard_class: Optional[str] = None


class BrainClient:
    """Async HTTP client for Brain service API.

    Usage:
        async with BrainClient() as client:
            response = await client.query(
                conversation_id="conv-123",
                user_id="user-456",
                prompt="What's the weather like?",
            )
            print(response.output)
    """

    def __init__(
        self,
        base_url: str = BRAIN_API_URL,
        timeout: float = 120.0,
    ) -> None:
        """Initialize Brain client.

        Args:
            base_url: Brain API base URL (default from BRAIN_API_URL env)
            timeout: Request timeout in seconds (default 120s for LLM calls)
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BrainClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check if Brain service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            client = self._ensure_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Brain health check failed: {e}")
            return False

    async def query(
        self,
        conversation_id: str,
        user_id: str,
        prompt: str,
        *,
        intent: str = "query",
        use_agent: bool = True,
        tool_mode: str = "auto",
        model: Optional[str] = None,
        provider: Optional[str] = None,
        allow_paid: bool = False,
        images: Optional[List[str]] = None,
    ) -> BrainResponse:
        """Send query to Brain API.

        Args:
            conversation_id: Conversation ID for context
            user_id: User identifier
            prompt: User's query text
            intent: Query intent (default "query")
            use_agent: Whether to use agent mode (default True)
            tool_mode: Tool usage mode (auto, enabled, disabled)
            model: Specific model to use (optional)
            provider: Specific provider to use (optional)
            allow_paid: Allow paid API calls (CAD, research)
            images: Base64-encoded images for vision queries

        Returns:
            BrainResponse with output and metadata

        Raises:
            httpx.HTTPError: On network/HTTP errors
            ValueError: On invalid response format
        """
        client = self._ensure_client()

        payload = {
            "conversationId": conversation_id,
            "userId": user_id,
            "intent": intent,
            "prompt": prompt,
            "useAgent": use_agent,
            "toolMode": tool_mode,
        }

        if model:
            payload["model"] = model
        if provider:
            payload["provider"] = provider
        if images:
            payload["images"] = images

        # Map allow_paid to force_tier if needed
        # (Brain API doesn't have allow_paid directly, but we can influence routing)

        logger.debug(f"Brain query: {prompt[:100]}...")

        try:
            response = await client.post("/api/query", json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract response fields
            result = data.get("result", {})
            routing = data.get("routing", {})

            return BrainResponse(
                output=result.get("output", ""),
                tier=routing.get("tier", "unknown"),
                confidence=routing.get("confidence", 0.0),
                latency_ms=routing.get("latencyMs", 0),
                cached=routing.get("cached", False),
                metadata=routing.get("metadata"),
                requires_confirmation=data.get("requiresConfirmation", False),
                confirmation_phrase=data.get("confirmationPhrase"),
                pending_tool=data.get("pendingTool"),
                hazard_class=data.get("hazardClass"),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Brain API error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Brain connection error: {e}")
            raise

    async def query_stream(
        self,
        conversation_id: str,
        user_id: str,
        prompt: str,
        *,
        intent: str = "query",
        use_agent: bool = True,
        tool_mode: str = "auto",
        model: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream query response from Brain API.

        Args:
            conversation_id: Conversation ID
            user_id: User identifier
            prompt: Query text
            intent: Query intent
            use_agent: Use agent mode
            tool_mode: Tool mode
            model: Specific model

        Yields:
            Chunks with 'type', 'delta', 'delta_thinking', 'done' fields
        """
        client = self._ensure_client()

        payload = {
            "conversationId": conversation_id,
            "userId": user_id,
            "intent": intent,
            "prompt": prompt,
            "useAgent": use_agent,
            "toolMode": tool_mode,
        }

        if model:
            payload["model"] = model

        try:
            async with client.stream("POST", "/api/query/stream", json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        import json
                        data = json.loads(line[6:])
                        yield data

        except httpx.HTTPError as e:
            logger.error(f"Brain stream error: {e}")
            yield {"type": "error", "error": str(e), "done": True}


# Singleton client instance
_client: Optional[BrainClient] = None


def get_brain_client() -> BrainClient:
    """Get or create singleton Brain client."""
    global _client
    if _client is None:
        _client = BrainClient()
    return _client


async def close_brain_client() -> None:
    """Close the singleton Brain client."""
    global _client
    if _client:
        await _client.close()
        _client = None
