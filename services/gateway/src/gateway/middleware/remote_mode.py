"""Middleware enforcing read-only access for remote clients."""

from __future__ import annotations

from typing import Iterable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

SAFE_METHODS: Iterable[str] = {"GET", "HEAD", "OPTIONS"}
HEADER = "X-Remote-Mode"
REMOTE_VALUE = "read-only"


class RemoteModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        remote_mode = request.headers.get(HEADER)
        if remote_mode == REMOTE_VALUE and request.method not in SAFE_METHODS:
            return Response(status_code=403, content="Remote mode is read-only")
        return await call_next(request)


__all__ = ["RemoteModeMiddleware"]
