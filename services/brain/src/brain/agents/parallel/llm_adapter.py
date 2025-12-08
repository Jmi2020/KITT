"""
Slot-aware LLM client adapter for parallel agent orchestration.

Wraps the existing MultiServerLlamaCppClient with:
- Automatic slot acquisition before generation
- Slot release after completion
- Soft tool allowlist injection into prompts
- Unified interface for all model tiers
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .types import ModelTier
from .registry import ENDPOINTS, KittyAgent, ModelEndpoint
from .slot_manager import SlotManager, get_slot_manager

logger = logging.getLogger("brain.parallel.llm")


class ParallelLLMClient:
    """
    Slot-aware LLM client for parallel agent execution.

    Manages slot acquisition/release and provides a unified interface
    across llama.cpp and Ollama endpoints.

    Usage:
        client = ParallelLLMClient()

        # Generate with automatic slot management
        response, metadata = await client.generate(
            tier=ModelTier.Q4_TOOLS,
            prompt="Research quantum computing",
            system_prompt="You are a research assistant",
            agent=researcher_agent,  # Optional - for soft tool guidance
        )
    """

    def __init__(
        self,
        slot_manager: Optional[SlotManager] = None,
        timeout: float = 120.0,
    ):
        """
        Initialize the parallel LLM client.

        Args:
            slot_manager: Custom slot manager (uses global singleton if None)
            timeout: HTTP request timeout in seconds
        """
        self._slot_manager = slot_manager or get_slot_manager()
        self._timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def generate(
        self,
        tier: ModelTier,
        prompt: str,
        system_prompt: str = "",
        agent: Optional[KittyAgent] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        allow_fallback: bool = True,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate completion with automatic slot management.

        Args:
            tier: Target model tier
            prompt: User prompt
            system_prompt: System prompt (will append agent tool guidance if provided)
            agent: Optional agent for soft tool guidance
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            tools: Optional tool definitions for tool calling
            allow_fallback: Whether to use fallback tier if primary is full

        Returns:
            Tuple of (response_text, metadata_dict)

        Raises:
            RuntimeError: If slot cannot be acquired
        """
        # Build system prompt with soft tool guidance
        full_system_prompt = system_prompt
        if agent and agent.tool_allowlist:
            tools_str = ", ".join(agent.tool_allowlist)
            full_system_prompt += f"\n\nRecommended tools: {tools_str}"

        # Determine fallback tier
        fallback_tier = agent.fallback_tier if agent else None

        # Acquire slot
        actual_tier, acquired = await self._slot_manager.acquire_slot(
            tier=tier,
            allow_fallback=allow_fallback,
            fallback_tier=fallback_tier,
        )

        if not acquired:
            raise RuntimeError(
                f"Could not acquire slot on {tier.value} "
                f"(or fallback {fallback_tier.value if fallback_tier else 'none'})"
            )

        try:
            start_time = time.perf_counter()

            endpoint = ENDPOINTS.get(actual_tier)
            if not endpoint:
                raise ValueError(f"Unknown tier: {actual_tier}")

            # Route to appropriate generation method
            if "11434" in endpoint.base_url:
                # Ollama endpoint
                result, meta = await self._generate_ollama(
                    endpoint=endpoint,
                    prompt=prompt,
                    system_prompt=full_system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            else:
                # llama.cpp endpoint
                result, meta = await self._generate_llamacpp(
                    endpoint=endpoint,
                    prompt=prompt,
                    system_prompt=full_system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tools,
                )

            # Add timing and tier info
            meta["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
            meta["tier"] = actual_tier.value
            meta["fallback_used"] = actual_tier != tier

            return result, meta

        finally:
            await self._slot_manager.release_slot(actual_tier)

    async def _generate_llamacpp(
        self,
        endpoint: ModelEndpoint,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate via llama.cpp /completion endpoint.

        Uses chat-style prompt formatting compatible with the model's template.
        """
        client = await self._get_client()

        # Build chat-style prompt
        full_prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{prompt}</s>\n<|assistant|>\n"

        payload = {
            "prompt": full_prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "stop": ["</s>", "<|user|>", "<|system|>"],
            "stream": False,
        }

        try:
            response = await client.post(
                f"{endpoint.base_url}/completion",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            return data.get("content", ""), {
                "model": endpoint.model_id,
                "tokens": data.get("tokens_predicted", 0),
                "tokens_prompt": data.get("tokens_evaluated", 0),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"llama.cpp request failed: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"llama.cpp request error: {e}")
            raise

    async def _generate_ollama(
        self,
        endpoint: ModelEndpoint,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate via Ollama /api/generate endpoint.

        Supports thinking mode for deep reasoning.
        """
        client = await self._get_client()

        payload = {
            "model": endpoint.model_id,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        # Add thinking mode if configured
        if endpoint.thinking_mode:
            payload["options"]["think"] = endpoint.thinking_mode

        try:
            response = await client.post(
                f"{endpoint.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            metadata = {
                "model": endpoint.model_id,
                "tokens": data.get("eval_count", 0),
                "tokens_prompt": data.get("prompt_eval_count", 0),
            }

            # Include thinking if present
            if "thinking" in data:
                metadata["thinking"] = data["thinking"]

            return data.get("response", ""), metadata
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama request failed: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Ollama request error: {e}")
            raise

    async def generate_for_agent(
        self,
        agent: KittyAgent,
        prompt: str,
        context: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate completion using agent's configured tier and settings.

        Convenience method that uses the agent's system prompt and defaults.

        Args:
            agent: The agent to use
            prompt: User prompt / task description
            context: Additional context from previous tasks
            max_tokens: Override agent's default max_tokens
            temperature: Override agent's default temperature

        Returns:
            Tuple of (response_text, metadata_dict)
        """
        # Build full prompt with context
        full_prompt = prompt
        if context:
            full_prompt = f"{context}\n\n{prompt}"

        return await self.generate(
            tier=agent.primary_tier,
            prompt=full_prompt,
            system_prompt=agent.build_system_prompt(include_tools=True),
            agent=agent,
            max_tokens=max_tokens or agent.max_tokens,
            temperature=temperature or agent.temperature,
            allow_fallback=agent.fallback_tier is not None,
        )

    def get_slot_status(self) -> Dict[str, Dict]:
        """Get current slot status across all tiers."""
        return self._slot_manager.get_status()

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance
_parallel_client: Optional[ParallelLLMClient] = None


def get_parallel_client() -> ParallelLLMClient:
    """Get or create the global parallel LLM client."""
    global _parallel_client
    if _parallel_client is None:
        _parallel_client = ParallelLLMClient()
    return _parallel_client


async def reset_parallel_client() -> None:
    """Reset the global parallel client (for testing)."""
    global _parallel_client
    if _parallel_client:
        await _parallel_client.close()
    _parallel_client = None
