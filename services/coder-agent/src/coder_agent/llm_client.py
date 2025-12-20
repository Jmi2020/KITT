"""
LLM client for communicating with llama.cpp servers.

Supports both OpenAI-compatible and native llama.cpp endpoints with automatic fallback.
Designed for offline-first operation with local llama.cpp instances.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class LlamaCppClient:
    """
    Client for llama.cpp servers supporting dual endpoint modes.

    Tries OpenAI-compatible /v1/chat/completions first, falls back to
    native /completion endpoint if needed. Fully offline operation.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 2,
    ) -> None:
        """
        Initialize llama.cpp client.

        Args:
            base_url: Base URL for llama.cpp server (e.g., http://localhost:8083)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.base_url = base_url or os.getenv("LLAMACPP_Q4_BASE", "http://localhost:8083")
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(timeout=timeout)

        # Track which endpoint mode works
        self._use_openai_compatible = True

        logger.info(f"Initialized LlamaCppClient with base_url={self.base_url}")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        Generate text completion from llama.cpp server.

        Args:
            prompt: User prompt/instruction
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = deterministic)
            stop: Optional stop sequences

        Returns:
            Generated text content

        Raises:
            httpx.HTTPError: If request fails after retries
        """
        # Try OpenAI-compatible endpoint first
        if self._use_openai_compatible:
            try:
                return await self._generate_openai(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop,
                )
            except (httpx.HTTPError, KeyError) as exc:
                logger.warning(
                    f"OpenAI-compatible endpoint failed: {exc}. Falling back to native."
                )
                self._use_openai_compatible = False

        # Fallback to native llama.cpp endpoint
        return await self._generate_native(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        Generate using OpenAI-compatible /v1/chat/completions endpoint.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stop: Optional stop sequences

        Returns:
            Generated text content
        """
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        if stop:
            payload["stop"] = stop

        url = f"{self.base_url}/v1/chat/completions"

        logger.debug(f"OpenAI-compatible request to {url}")
        response = await self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        logger.debug(f"OpenAI-compatible response: {len(content)} chars")
        return content.strip()

    async def _generate_native(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        Generate using native llama.cpp /completion endpoint.

        Args:
            prompt: User prompt (system prompt prepended if provided)
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stop: Optional stop sequences

        Returns:
            Generated text content
        """
        # Combine system and user prompts for native endpoint
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "prompt": full_prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        if stop:
            payload["stop"] = stop

        url = f"{self.base_url}/completion"

        logger.debug(f"Native llama.cpp request to {url}")
        response = await self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["content"]

        logger.debug(f"Native response: {len(content)} chars")
        return content.strip()

    async def health_check(self) -> bool:
        """
        Check if llama.cpp server is responsive.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            # Try health endpoint first
            health_url = f"{self.base_url}/health"
            response = await self.client.get(health_url, timeout=5.0)

            if response.status_code == 200:
                logger.debug(f"Server healthy at {health_url}")
                return True

        except httpx.HTTPError:
            pass

        # Fallback: try generating a minimal completion
        try:
            result = await self.generate(
                prompt="Hello",
                max_tokens=5,
                temperature=0.0,
            )
            logger.debug(f"Health check via generation successful: {result[:50]}")
            return len(result) > 0

        except Exception as exc:
            logger.error(f"Health check failed: {exc}")
            return False


class CoderLLMClient:
    """
    High-level LLM client for coding tasks with model routing.

    Local-first: Uses Ollama with Devstral 2 as primary.
    Fallback to llama.cpp servers if Ollama unavailable:
    - Q4 (fast, 8083): Quick planning, test generation
    - F16 (precise, 8082): Code generation, refinement
    """

    def __init__(self) -> None:
        """Initialize coder LLM client with Ollama-first routing."""
        # Local-first: Ollama with Devstral 2 (primary)
        ollama_base = os.getenv("OLLAMA_CODER_BASE", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_CODER_MODEL", "devstral:123b")
        self.ollama_client = LlamaCppClient(
            base_url=ollama_base,
            timeout=180,  # Longer timeout for large model
        )

        # Fallback: Q4 server for fast operations
        self.q4_client = LlamaCppClient(
            base_url=os.getenv("LLAMACPP_Q4_BASE", "http://localhost:8083"),
            timeout=60,
        )

        # Fallback: F16 server for precise operations
        self.f16_client = LlamaCppClient(
            base_url=os.getenv("LLAMACPP_F16_BASE", "http://localhost:8082"),
            timeout=120,
        )

        # Track which backend to use
        self._use_ollama = True
        self._ollama_checked = False

        logger.info(
            f"Initialized CoderLLMClient: ollama={ollama_base}, "
            f"model={self.ollama_model}, fallback=Q4/F16"
        )

    async def close(self) -> None:
        """Close all HTTP clients."""
        await self.ollama_client.close()
        await self.q4_client.close()
        await self.f16_client.close()

    async def _get_client(self, prefer_fast: bool = False) -> LlamaCppClient:
        """
        Get the best available client.

        Local-first: Try Ollama first, fall back to llama.cpp servers.

        Args:
            prefer_fast: If True and Ollama unavailable, use Q4 over F16

        Returns:
            Best available LLM client
        """
        # Check Ollama health once per session
        if not self._ollama_checked:
            self._use_ollama = await self.ollama_client.health_check()
            self._ollama_checked = True
            if self._use_ollama:
                logger.info("Using Ollama with Devstral 2")
            else:
                logger.warning("Ollama unavailable, falling back to llama.cpp")

        if self._use_ollama:
            return self.ollama_client

        # Fallback to llama.cpp servers
        return self.q4_client if prefer_fast else self.f16_client

    async def plan(
        self,
        user_request: str,
        system_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate implementation plan.

        Local-first: Uses Ollama with Devstral 2, falls back to Q4.

        Args:
            user_request: User's coding request
            system_prompt: System instructions
            max_tokens: Maximum tokens for plan

        Returns:
            Implementation plan text
        """
        client = await self._get_client(prefer_fast=True)
        logger.info(f"Generating plan with {'Ollama' if self._use_ollama else 'Q4'}")
        return await client.generate(
            prompt=user_request,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.3,  # Low temp for structured planning
        )

    async def code(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 6144,
    ) -> str:
        """
        Generate code.

        Local-first: Uses Ollama with Devstral 2, falls back to F16.

        Args:
            prompt: Code generation prompt with plan context
            system_prompt: System instructions
            max_tokens: Maximum tokens for code

        Returns:
            Generated Python code
        """
        client = await self._get_client(prefer_fast=False)
        logger.info(f"Generating code with {'Ollama' if self._use_ollama else 'F16'}")
        return await client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.2,  # Low temp for correct code
        )

    async def tests(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """
        Generate pytest tests.

        Local-first: Uses Ollama with Devstral 2, falls back to Q4.

        Args:
            prompt: Test generation prompt with code context
            system_prompt: System instructions
            max_tokens: Maximum tokens for tests

        Returns:
            Generated pytest test code
        """
        client = await self._get_client(prefer_fast=True)
        logger.info(f"Generating tests with {'Ollama' if self._use_ollama else 'Q4'}")
        return await client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.3,  # Low temp for structured tests
        )

    async def refine(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 6144,
    ) -> str:
        """
        Refine code based on test failures.

        Local-first: Uses Ollama with Devstral 2, falls back to F16.

        Args:
            prompt: Refinement prompt with error context
            system_prompt: System instructions
            max_tokens: Maximum tokens for refined code

        Returns:
            Refined Python code
        """
        client = await self._get_client(prefer_fast=False)
        logger.info(f"Refining code with {'Ollama' if self._use_ollama else 'F16'}")
        return await client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.2,  # Low temp for correct fixes
        )

    async def summarize(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate summary with usage examples.

        Local-first: Uses Ollama with Devstral 2, falls back to Q4.

        Args:
            prompt: Summary prompt with results context
            system_prompt: System instructions
            max_tokens: Maximum tokens for summary

        Returns:
            Markdown summary with usage examples
        """
        client = await self._get_client(prefer_fast=True)
        logger.info(f"Generating summary with {'Ollama' if self._use_ollama else 'Q4'}")
        return await client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.5,  # Moderate temp for readable summaries
        )

    async def health_check(self) -> Dict[str, bool]:
        """
        Check health of all LLM servers.

        Returns:
            Dictionary of server health status
        """
        health = {
            "ollama": await self.ollama_client.health_check(),
            "q4": await self.q4_client.health_check(),
            "f16": await self.f16_client.health_check(),
        }

        return health
