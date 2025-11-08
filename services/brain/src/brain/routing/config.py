# noqa: D401
"""Routing configuration models and helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field

from common.config import settings
from brain.config import get_performance_settings


_performance = get_performance_settings()


class LlamaCppConfig(BaseModel):
    host: str = Field(default=settings.llamacpp_host)
    n_predict: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.1, ge=0.0)  # Low temperature (0.0-0.2) required for reliable Llama 3.3 tool calling
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    stop_tokens: List[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=60.0, ge=1.0)
    stream: bool = False
    api_path: str = Field(default="/completion")
    model_alias: Optional[str] = None


class Thresholds(BaseModel):
    local_confidence: float = Field(_performance.local_confidence, ge=0.0, le=1.0)
    frontier_confidence: float = Field(_performance.frontier_confidence, ge=0.0, le=1.0)


class RoutingConfig(BaseModel):
    thresholds: Thresholds = Thresholds()
    local_models: List[str] = Field(default_factory=lambda: settings.local_models)
    llamacpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    mlx_endpoint: str = Field(default="http://localhost:8081")
    semantic_cache_enabled: bool = _performance.semantic_cache_enabled


@lru_cache(maxsize=1)
def get_routing_config() -> RoutingConfig:
    stop_tokens_env = os.getenv("LLAMACPP_STOP", "")
    stop_tokens = [token.strip() for token in stop_tokens_env.split(",") if token.strip()]
    llama_cfg = LlamaCppConfig(
        host=os.getenv("LLAMACPP_HOST", settings.llamacpp_host),
        n_predict=int(os.getenv("LLAMACPP_N_PREDICT", "512")),
        temperature=float(os.getenv("LLAMACPP_TEMPERATURE", "0.1")),
        top_p=float(os.getenv("LLAMACPP_TOP_P", "0.95")),
        repeat_penalty=float(os.getenv("LLAMACPP_REPEAT_PENALTY", "1.1")),
        stop_tokens=stop_tokens,
        timeout_seconds=float(os.getenv("LLAMACPP_TIMEOUT", "60")),
        stream=os.getenv("LLAMACPP_STREAM", "false").lower() in {"1", "true", "yes", "on"},
        api_path=os.getenv("LLAMACPP_API_PATH", "/completion"),
        model_alias=None,
    )
    alias = os.getenv("LLAMACPP_MODEL_ALIAS")
    if alias:
        llama_cfg.model_alias = alias

    primary = os.getenv("LOCAL_MODEL_PRIMARY")
    secondary = os.getenv("LOCAL_MODEL_CODER")
    overrides = [value for value in (primary, secondary) if value]
    local_models = overrides or settings.local_models

    return RoutingConfig(local_models=local_models, llamacpp=llama_cfg)


__all__ = ["RoutingConfig", "get_routing_config", "Thresholds"]
