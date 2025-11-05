"""Application-wide configuration management using Pydantic settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration shared across services.

    Environment variables mirror the compose setup and allow overrides per service.
    """

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="allow")

    environment: str = "development"
    service_name: str = "jarvis-service"

    # Messaging / MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None

    # Redis / cache
    redis_url: str = "redis://localhost:6379/0"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "jarvis"
    postgres_user: str = "jarvis"
    postgres_password: str = "changeme"

    # MinIO / artifact store
    minio_endpoint: str = "http://localhost:9000"
    minio_bucket: str = "jarvis-artifacts"
    minio_access_key: Optional[str] = None
    minio_secret_key: Optional[str] = None

    # Home Assistant
    home_assistant_base_url: str = "http://homeassistant:8123"
    home_assistant_token: Optional[str] = None

    # Security / OAuth
    secret_key: str = "super-secret"
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"

    # Model routing
    local_models: List[str] = ["qwen2.5-coder-32b", "mistral-7b"]

    # Observability
    prometheus_url: str = "http://localhost:9090"

    # Model endpoints
    ollama_host: str = "http://ollama:11434"
    mlx_endpoint: str = "http://localhost:8091"
    semantic_cache_enabled: bool = True

    # External providers
    perplexity_base_url: str = "https://api.perplexity.ai"
    perplexity_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

    # CAD providers
    zoo_api_base: str = "https://api.zoo.dev"
    zoo_api_key: Optional[str] = None
    tripo_api_base: str = "https://api.tripo.ai"
    tripo_api_key: Optional[str] = None

    # UniFi Access
    unifi_access_base_url: Optional[str] = None
    unifi_access_token: Optional[str] = None

    # Hazard signing
    hazard_signing_key: Optional[str] = None

    # Voice
    voice_system_prompt: Optional[str] = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache configuration for the current process."""

    return Settings()  # type: ignore[arg-type]


settings = get_settings()
