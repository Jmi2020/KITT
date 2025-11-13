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
    service_name: str = "kitty-service"
    user_name: str = "operator"
    primary_locale: str = "en-US"
    verbosity: int = 3

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
    postgres_db: str = "kitty"
    postgres_user: str = "kitty"
    postgres_password: str = "changeme"

    # MinIO / artifact store
    minio_endpoint: str = "http://localhost:9000"
    minio_bucket: str = "kitty-artifacts"
    minio_access_key: Optional[str] = None
    minio_secret_key: Optional[str] = None

    # Home Assistant
    home_assistant_base_url: str = "http://homeassistant:8123"
    home_assistant_token: Optional[str] = None
    home_assistant_auto_discover: bool = False
    home_assistant_discovery_timeout: float = 5.0

    # Fabrication / Multi-Printer Control
    printer_config: str = "config/printers.yaml"

    # Network Discovery
    discovery_port: int = 8500
    discovery_scan_interval_minutes: int = 15
    discovery_enable_periodic_scans: bool = True
    discovery_enable_mdns: bool = True
    discovery_enable_ssdp: bool = True
    discovery_enable_bamboo_udp: bool = True
    discovery_enable_snapmaker_udp: bool = True
    discovery_enable_network_scan: bool = False
    discovery_subnets: List[str] = ["192.168.1.0/24"]  # Comma-separated CIDRs to scan
    discovery_ping_sweep_interval_minutes: int = 60  # How often to run full ping sweep

    # Bamboo Labs H2D
    bamboo_ip: str = "192.168.1.100"
    bamboo_serial: str = "01P45165616"
    bamboo_access_code: str = ""
    bamboo_mqtt_host: Optional[str] = None
    bamboo_mqtt_port: int = 1883
    h2d_build_width: int = 250
    h2d_build_depth: int = 250
    h2d_build_height: int = 250

    # Elegoo Giga (Klipper)
    elegoo_ip: str = "192.168.1.200"
    elegoo_moonraker_port: int = 7125
    orangestorm_giga_build_width: int = 800
    orangestorm_giga_build_depth: int = 800
    orangestorm_giga_build_height: int = 1000

    # Snapmaker Artisan
    snapmaker_ip: str = "192.168.1.150"
    snapmaker_port: int = 8888
    snapmaker_token: Optional[str] = None

    # Security / OAuth
    secret_key: str = "super-secret"
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"

    # Model routing
    local_models: List[str] = ["kitty-primary", "kitty-coder"]

    # Observability
    prometheus_url: str = "http://localhost:9090"

    # Model endpoints
    llamacpp_host: str = "http://localhost:8080"
    mlx_endpoint: str = "http://localhost:8091"
    semantic_cache_enabled: bool = True
    agentic_mode_enabled: bool = False

    # Vision / image search providers
    searxng_base_url: Optional[str] = None
    image_search_safesearch: str = "moderate"
    brave_search_api_key: Optional[str] = None
    brave_search_endpoint: str = "https://api.search.brave.com/res/v1/images/search"
    image_search_provider: str = "auto"
    internal_searxng_base_url: Optional[str] = None

    # External providers
    perplexity_base_url: str = "https://api.perplexity.ai"
    perplexity_api_key: Optional[str] = None
    perplexity_model_search: str = "sonar"
    perplexity_model_reasoning: str = "sonar-reasoning-pro"
    perplexity_model_research: str = "sonar-pro"
    openai_base_url: str = "https://api.openai.com"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

    # CAD providers
    zoo_api_base: str = "https://api.zoo.dev"
    zoo_api_key: Optional[str] = None
    tripo_api_base: str = "https://api.tripo3d.ai/v2/openapi"
    tripo_api_key: Optional[str] = None
    tripo_max_image_refs: int = 2
    tripo_model_version: Optional[str] = None
    tripo_texture_quality: Optional[str] = None
    tripo_texture_alignment: Optional[str] = None
    tripo_orientation: Optional[str] = None
    tripo_poll_interval: float = 3.0
    tripo_poll_timeout: float = 900.0
    tripo_convert_enabled: bool = False
    tripo_stl_format: str = "binary"
    tripo_face_limit: Optional[int] = None
    tripo_unit: str = "millimeters"

    # UniFi Access
    unifi_access_base_url: Optional[str] = None
    unifi_access_token: Optional[str] = None

    # Hazard signing
    hazard_signing_key: Optional[str] = None

    # Voice
    voice_system_prompt: Optional[str] = None

    # Autonomous Operations
    autonomous_enabled: bool = False
    autonomous_daily_budget_usd: float = 5.00
    autonomous_idle_threshold_minutes: int = 120
    autonomous_cpu_threshold_percent: float = 20.0
    autonomous_memory_threshold_percent: float = 70.0
    autonomous_user_id: str = "system-autonomous"

    # Phase 3: Outcome Tracking & Learning
    outcome_measurement_enabled: bool = True
    outcome_measurement_window_days: int = 30
    outcome_measurement_schedule: str = "0 14 * * *"  # Daily 6am PST (14:00 UTC)
    feedback_loop_enabled: bool = True
    feedback_loop_min_samples: int = 10  # Minimum outcomes before adjusting
    feedback_loop_adjustment_max: float = 1.5  # Maximum 1.5x boost


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache configuration for the current process."""

    return Settings()  # type: ignore[arg-type]


settings = get_settings()
