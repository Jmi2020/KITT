# noqa: D401
"""Data models for KITTY Model Manager."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ToolCallFormat(Enum):
    """Tool calling format for different model families."""

    QWEN_XML = "qwen_xml"
    MISTRAL_JSON = "mistral_json"
    GEMMA_FUNCTION = "gemma_function"
    GENERIC_XML = "generic_xml"


class QuantizationType(Enum):
    """GGUF quantization types."""

    FP16 = "fp16"
    FP32 = "fp32"
    Q8_0 = "q8_0"
    Q6_K = "q6_k"
    Q5_K_M = "q5_k_m"
    Q5_K_S = "q5_k_s"
    Q4_K_M = "q4_k_m"
    Q4_K_S = "q4_k_s"
    Q3_K_M = "q3_k_m"
    Q3_K_S = "q3_k_s"
    Q2_K = "q2_k"
    UNKNOWN = "unknown"


class ServerStatus(Enum):
    """Server lifecycle states."""

    STOPPED = "stopped"
    STARTING = "starting"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"
    CRASHED = "crashed"


class ModelInfo(BaseModel):
    """Information about a GGUF model file or model family."""

    # Identity
    path: Path
    name: str
    family: str  # e.g., "Qwen2.5-72B-Instruct-GGUF"

    # Model properties
    quantization: QuantizationType = QuantizationType.UNKNOWN
    tool_format: ToolCallFormat = ToolCallFormat.GENERIC_XML

    # File metadata
    size_bytes: int
    file_count: int = 1  # Number of shards (1 for single-file models)
    shard_index: Optional[int] = None  # e.g., 1 from "00001-of-00042"
    shard_total: Optional[int] = None  # e.g., 42 from "00001-of-00042"
    is_complete: bool = True  # All shards present

    # Estimated properties
    estimated_params_billions: Optional[float] = None
    estimated_memory_gb: Optional[float] = None

    # User metadata
    favorite: bool = False
    last_used: Optional[datetime] = None
    notes: Optional[str] = None

    # Performance data (from benchmarks)
    avg_tokens_per_sec: Optional[float] = None
    avg_latency_ms: Optional[float] = None

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, v: Any) -> Path:
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v

    @property
    def display_name(self) -> str:
        """Human-readable name for display."""
        quant = self.quantization.value if self.quantization != QuantizationType.UNKNOWN else ""
        if self.shard_total and self.shard_total > 1:
            return f"{self.name} ({quant}, {self.shard_total} shards)"
        return f"{self.name} ({quant})" if quant else self.name

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024**3)

    @property
    def is_split(self) -> bool:
        """Whether this is a split/sharded model."""
        return self.shard_total is not None and self.shard_total > 1


class ServerConfig(BaseModel):
    """Configuration for llama.cpp server."""

    # Model selection
    primary_model: str  # Relative path from models_dir
    models_dir: Path
    model_alias: str = "kitty-primary"

    # Server settings
    host: str = "localhost"
    port: int = 8080
    binary: str = "llama-server"

    # Context and generation
    context_size: int = 8192
    n_predict: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    repeat_penalty: float = 1.1

    # GPU/Performance
    n_gpu_layers: int = 999  # Offload all layers
    threads: int = 20  # P-cores on M3 Ultra
    batch_size: int = 4096
    ubatch_size: int = 1024
    parallel: int = 6
    flash_attention: bool = True

    # Tool calling
    tool_calling: bool = False

    # Stop tokens
    stop_tokens: List[str] = Field(default_factory=list)

    # Extra arguments
    extra_args: List[str] = Field(default_factory=list)

    @field_validator("models_dir", mode="before")
    @classmethod
    def validate_models_dir(cls, v: Any) -> Path:
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v

    @property
    def full_model_path(self) -> Path:
        """Absolute path to primary model."""
        return self.models_dir / self.primary_model

    @property
    def endpoint(self) -> str:
        """Server endpoint URL."""
        return f"http://{self.host}:{self.port}"

    def to_command(self) -> List[str]:
        """Generate llama-server command arguments."""
        cmd = [
            self.binary,
            "-m", str(self.full_model_path),
            "--host", self.host,
            "--port", str(self.port),
            "-c", str(self.context_size),
            "-n", str(self.n_predict),
            "--temp", str(self.temperature),
            "--top-p", str(self.top_p),
            "--repeat-penalty", str(self.repeat_penalty),
            "-ngl", str(self.n_gpu_layers),
            "-t", str(self.threads),
            "-b", str(self.batch_size),
            "-ub", str(self.ubatch_size),
            "-np", str(self.parallel),
        ]

        if self.flash_attention:
            cmd.append("-fa")

        if self.tool_calling:
            cmd.extend(["--jinja", "-fa"])

        if self.stop_tokens:
            for token in self.stop_tokens:
                cmd.extend(["--stop", token])

        if self.model_alias:
            cmd.extend(["-a", self.model_alias])

        # Add any extra arguments
        cmd.extend(self.extra_args)

        return cmd


class ServerMetrics(BaseModel):
    """Performance metrics from running server."""

    # Request stats
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Latency stats
    avg_latency_ms: Optional[float] = None
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None

    # Throughput stats
    avg_tokens_per_sec: Optional[float] = None
    total_tokens_generated: int = 0

    # Resource usage
    memory_used_gb: Optional[float] = None
    gpu_utilization_pct: Optional[float] = None
    gpu_memory_used_gb: Optional[float] = None

    # Slot usage
    active_slots: int = 0
    max_slots: int = 6

    # Timestamp
    last_updated: datetime = Field(default_factory=datetime.now)


class ServerState(BaseModel):
    """Current state of llama.cpp server."""

    # Status
    status: ServerStatus = ServerStatus.STOPPED
    pid: Optional[int] = None

    # Loaded model
    loaded_model: Optional[str] = None
    loaded_model_alias: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None
    uptime_seconds: float = 0.0

    # Error handling
    error_message: Optional[str] = None
    restart_count: int = 0
    last_restart_at: Optional[datetime] = None

    # Metrics
    metrics: ServerMetrics = Field(default_factory=ServerMetrics)

    @property
    def is_running(self) -> bool:
        """Whether server is currently running."""
        return self.status in (ServerStatus.STARTING, ServerStatus.LOADING, ServerStatus.READY)

    @property
    def is_ready(self) -> bool:
        """Whether server is ready to accept requests."""
        return self.status == ServerStatus.READY

    @property
    def startup_duration_seconds(self) -> Optional[float]:
        """Time taken from start to ready."""
        if self.started_at and self.ready_at:
            return (self.ready_at - self.started_at).total_seconds()
        return None


class ModelRegistry(BaseModel):
    """Registry of all discovered models."""

    models: List[ModelInfo] = Field(default_factory=list)
    last_scan: Optional[datetime] = None
    scan_duration_seconds: float = 0.0

    # Grouping
    families: Dict[str, List[ModelInfo]] = Field(default_factory=dict)

    def add_model(self, model: ModelInfo) -> None:
        """Add a model to the registry."""
        self.models.append(model)
        if model.family not in self.families:
            self.families[model.family] = []
        self.families[model.family].append(model)

    def get_by_name(self, name: str) -> Optional[ModelInfo]:
        """Get model by name."""
        for model in self.models:
            if model.name == name:
                return model
        return None

    def get_by_family(self, family: str) -> List[ModelInfo]:
        """Get all models in a family."""
        return self.families.get(family, [])

    def get_favorites(self) -> List[ModelInfo]:
        """Get all favorite models."""
        return [m for m in self.models if m.favorite]

    def get_recent(self, limit: int = 5) -> List[ModelInfo]:
        """Get recently used models."""
        recent = [m for m in self.models if m.last_used is not None]
        recent.sort(key=lambda m: m.last_used or datetime.min, reverse=True)
        return recent[:limit]

    @property
    def total_models(self) -> int:
        """Total number of models."""
        return len(self.models)

    @property
    def total_families(self) -> int:
        """Total number of model families."""
        return len(self.families)

    @property
    def total_size_gb(self) -> float:
        """Total size of all models in GB."""
        return sum(m.size_gb for m in self.models)


class HealthCheckResult(BaseModel):
    """Result of a health check poll."""

    success: bool
    status_code: Optional[int] = None
    response_time_ms: float
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


__all__ = [
    "ToolCallFormat",
    "QuantizationType",
    "ServerStatus",
    "ModelInfo",
    "ServerConfig",
    "ServerMetrics",
    "ServerState",
    "ModelRegistry",
    "HealthCheckResult",
]
