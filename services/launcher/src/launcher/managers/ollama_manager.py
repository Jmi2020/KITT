"""Ollama (GPT-OSS) server monitoring."""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx


@dataclass
class OllamaStatus:
    """Status of the Ollama server (GPT-OSS stack)."""

    running: bool
    url: str
    version: Optional[str] = None
    model_count: int = 0
    models: list[str] = None
    error: Optional[str] = None


class OllamaManager:
    """Lightweight health checker for Ollama."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 2.5):
        """
        Args:
            base_url: Ollama base URL (default: OLLAMA_HOST env or http://localhost:11434)
            timeout: HTTP timeout seconds
        """
        import os

        env_url = base_url or os.getenv("OLLAMA_HOST") or "http://localhost:11434"
        parsed = urlparse(env_url)
        if not parsed.scheme:
            env_url = f"http://{env_url}"
        self.base_url = env_url.rstrip("/")
        self.timeout = timeout

    async def get_status(self) -> OllamaStatus:
        """Check Ollama health by hitting /api/tags and /api/version."""
        tags_url = f"{self.base_url}/api/tags"
        version_url = f"{self.base_url}/api/version"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                tags_resp = await client.get(tags_url)
                if tags_resp.status_code != 200:
                    return OllamaStatus(
                        running=False,
                        url=self.base_url,
                        error=f"HTTP {tags_resp.status_code}",
                        models=[],
                    )

                tags = tags_resp.json().get("models", []) or []
                models = [m.get("name") for m in tags if isinstance(m, dict)]

                version = None
                try:
                    ver_resp = await client.get(version_url)
                    if ver_resp.status_code == 200:
                        version = ver_resp.json().get("version")
                except Exception:
                    # Version is optional; ignore failures
                    pass

                return OllamaStatus(
                    running=True,
                    url=self.base_url,
                    version=version,
                    model_count=len(models),
                    models=models,
                    error=None,
                )

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                return OllamaStatus(
                    running=False,
                    url=self.base_url,
                    error=f"Connection failed: {type(exc).__name__}",
                    models=[],
                )
            except Exception as exc:  # pragma: no cover - defensive
                return OllamaStatus(
                    running=False,
                    url=self.base_url,
                    error=f"Error: {exc}",
                    models=[],
                )
