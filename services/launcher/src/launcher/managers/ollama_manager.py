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

        env_url = base_url or os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL")
        self.explicit_url = env_url.rstrip("/") if env_url else None
        self.timeout = timeout

    async def get_status(self) -> OllamaStatus:
        """Check Ollama health by hitting /api/tags and /api/version."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            errors = []
            for base in self._candidate_urls():
                tags_url = f"{base}/api/tags"
                version_url = f"{base}/api/version"
                try:
                    tags_resp = await client.get(tags_url)
                    if tags_resp.status_code != 200:
                        errors.append(f"{base} HTTP {tags_resp.status_code}")
                        continue

                    tags = tags_resp.json().get("models", []) or []
                    models = [m.get("name") for m in tags if isinstance(m, dict)]

                    version = None
                    try:
                        ver_resp = await client.get(version_url)
                        if ver_resp.status_code == 200:
                            version = ver_resp.json().get("version")
                    except Exception:
                        pass  # version optional

                    return OllamaStatus(
                        running=True,
                        url=base,
                        version=version,
                        model_count=len(models),
                        models=models,
                        error=None,
                    )

                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    errors.append(f"{base} connection failed: {type(exc).__name__}")
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(f"{base} error: {exc}")

        # If we get here, all candidates failed
        detail = "; ".join(errors) if errors else "unreachable"
        fallback = self.explicit_url or "http://localhost:11434"
        return OllamaStatus(
            running=False,
            url=fallback,
            error=detail,
            models=[],
        )

    def _candidate_urls(self) -> list[str]:
        """Generate possible Ollama base URLs to probe in order."""
        hosts = []
        if self.explicit_url:
            hosts.append(self.explicit_url)
        # Common defaults
        hosts.extend(
            [
                "http://localhost:11434",
                "http://127.0.0.1:11434",
                "http://host.docker.internal:11434",
            ]
        )
        # Normalize and de-dup while preserving order
        seen = set()
        cleaned = []
        for h in hosts:
            parsed = urlparse(h)
            base = h
            if not parsed.scheme:
                base = f"http://{h}"
            base = base.rstrip("/")
            if base not in seen:
                seen.add(base)
                cleaned.append(base)
        return cleaned
