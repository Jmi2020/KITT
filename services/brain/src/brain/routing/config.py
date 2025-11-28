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
    n_predict: int = Field(default=896, ge=1)
    temperature: float = Field(default=0.1, ge=0.0)  # Low temperature (0.0-0.2) required for reliable Llama 3.3 tool calling
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    stop_tokens: List[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=90.0, ge=1.0)
    stream: bool = False
    api_path: str = Field(default="/completion")
    model_alias: Optional[str] = None


class OllamaConfig(BaseModel):
    """Configuration for Ollama reasoning client (GPT-OSS with thinking mode)."""
    host: str = Field(default="http://localhost:11434")
    model: str = Field(default="gpt-oss:120b")
    think: str = Field(default="medium")  # low | medium | high
    timeout_seconds: float = Field(default=120.0, ge=1.0)
    keep_alive: str = Field(default="5m")


class Thresholds(BaseModel):
    local_confidence: float = Field(_performance.local_confidence, ge=0.0, le=1.0)
    frontier_confidence: float = Field(_performance.frontier_confidence, ge=0.0, le=1.0)


class RoutingConfig(BaseModel):
    thresholds: Thresholds = Thresholds()
    local_models: List[str] = Field(default_factory=lambda: settings.local_models)
    llamacpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    local_reasoner_provider: str = Field(default="llamacpp")  # ollama | llamacpp
    mlx_endpoint: str = Field(default="http://localhost:8081")
    semantic_cache_enabled: bool = _performance.semantic_cache_enabled

    # Semantic tool selection - reduces context usage by ~90% for large tool sets
    use_semantic_tool_selection: bool = Field(default=True)
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    tool_search_top_k: int = Field(default=5, ge=1, le=20)
    tool_search_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


@lru_cache(maxsize=1)
def get_routing_config() -> RoutingConfig:
    stop_tokens_env = os.getenv("LLAMACPP_STOP", "")
    stop_tokens = [token.strip() for token in stop_tokens_env.split(",") if token.strip()]
    llama_cfg = LlamaCppConfig(
        host=os.getenv("LLAMACPP_HOST", settings.llamacpp_host),
        n_predict=int(os.getenv("LLAMACPP_N_PREDICT", "896")),
        temperature=float(os.getenv("LLAMACPP_TEMPERATURE", "0.1")),
        top_p=float(os.getenv("LLAMACPP_TOP_P", "0.95")),
        repeat_penalty=float(os.getenv("LLAMACPP_REPEAT_PENALTY", "1.1")),
        stop_tokens=stop_tokens,
        timeout_seconds=float(os.getenv("LLAMACPP_TIMEOUT", "1200")),
        stream=os.getenv("LLAMACPP_STREAM", "false").lower() in {"1", "true", "yes", "on"},
        api_path=os.getenv("LLAMACPP_API_PATH", "/completion"),
        model_alias=None,
    )
    alias = os.getenv("LLAMACPP_MODEL_ALIAS")
    if alias:
        llama_cfg.model_alias = alias

    # Ollama configuration (GPT-OSS with thinking mode)
    ollama_cfg = OllamaConfig(
        host=os.getenv("OLLAMA_HOST", settings.ollama_host),
        model=os.getenv("OLLAMA_MODEL", settings.ollama_model),
        think=os.getenv("OLLAMA_THINK", settings.ollama_think),
        timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_S", str(settings.ollama_timeout_s))),
        keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", settings.ollama_keep_alive),
    )

    primary = os.getenv("LOCAL_MODEL_PRIMARY")
    secondary = os.getenv("LOCAL_MODEL_CODER")
    overrides = [value for value in (primary, secondary) if value]
    local_models = overrides or settings.local_models

    # Router provider selection
    local_reasoner_provider = os.getenv("LOCAL_REASONER_PROVIDER", settings.local_reasoner_provider)

    # Semantic tool selection config
    use_semantic_tool_selection = os.getenv(
        "USE_SEMANTIC_TOOL_SELECTION", "true"
    ).lower() in {"1", "true", "yes", "on"}
    embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    tool_search_top_k = int(os.getenv("TOOL_SEARCH_TOP_K", "5"))
    tool_search_threshold = float(os.getenv("TOOL_SEARCH_THRESHOLD", "0.3"))

    return RoutingConfig(
        local_models=local_models,
        llamacpp=llama_cfg,
        ollama=ollama_cfg,
        local_reasoner_provider=local_reasoner_provider,
        use_semantic_tool_selection=use_semantic_tool_selection,
        embedding_model=embedding_model,
        tool_search_top_k=tool_search_top_k,
        tool_search_threshold=tool_search_threshold,
    )


__all__ = ["RoutingConfig", "get_routing_config", "Thresholds"]
