# noqa: D401
"""Routing configuration models and helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import BaseModel, Field

from common.config import settings


class Thresholds(BaseModel):
    local_confidence: float = Field(0.75, ge=0.0, le=1.0)
    frontier_confidence: float = Field(0.4, ge=0.0, le=1.0)


class RoutingConfig(BaseModel):
    thresholds: Thresholds = Thresholds()
    local_models: List[str] = Field(default_factory=lambda: settings.local_models)
    ollama_host: str = Field(default="http://ollama:11434")
    mlx_endpoint: str = Field(default="http://localhost:8081")
    semantic_cache_enabled: bool = True


@lru_cache(maxsize=1)
def get_routing_config() -> RoutingConfig:
    return RoutingConfig()


__all__ = ["RoutingConfig", "get_routing_config", "Thresholds"]
