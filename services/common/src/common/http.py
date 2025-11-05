"""Standard HTTP client helpers for external integrations."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional

import httpx


def _build_headers(bearer_token: Optional[str], api_key: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {"User-Agent": "KITTY/1.0"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if api_key:
        headers["x-api-key"] = api_key
    return headers


@asynccontextmanager
def http_client(  # type: ignore[return-type]
    base_url: Optional[str] = None,
    bearer_token: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 30.0,
) -> AsyncIterator[httpx.AsyncClient]:
    """Provide a configured async HTTP client."""

    headers = _build_headers(bearer_token, api_key)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=headers) as client:
        yield client


__all__ = ["http_client"]
