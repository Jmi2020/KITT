# noqa: D401
"""Routing configuration utilities."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter

from common.config import settings
from ..routing.config import get_routing_config

router = APIRouter(prefix="/api/routing", tags=["routing"])


@router.get("/models")
def get_models() -> Dict[str, List[str]]:
    """Expose available local and remote model identifiers."""

    cfg = get_routing_config()
    local_models = cfg.local_models or []
    response = {
        "local": local_models,
        "aliases": {
            "primary": settings.local_models[0] if settings.local_models else None,
        },
    }
    if settings.openai_model:
        response["frontier"] = [settings.openai_model]
    return response


__all__ = ["router"]
