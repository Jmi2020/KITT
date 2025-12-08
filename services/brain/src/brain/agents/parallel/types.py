"""
Core types for the parallel agent orchestration system.

Provides foundational data structures for task tracking, model tiers,
and execution metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelTier(Enum):
    """
    Maps to specific LLM endpoints with known capacities.

    Each tier represents a model endpoint optimized for specific tasks:
    - Q4_TOOLS: Fast tool calling and routing (Athene V2)
    - GPTOSS_REASON: Deep reasoning with thinking mode (GPT-OSS 120B)
    - VISION: Multimodal image analysis (Llama 3.2 Vision)
    - CODER: Code generation (Qwen 32B Coder)
    - SUMMARY: Text compression and summarization (Hermes 8B)
    - MCP_EXTERNAL: External MCP tools (async, no slot limit)
    """
    Q4_TOOLS = "q4_tools"
    GPTOSS_REASON = "gptoss_reason"
    VISION = "vision"
    CODER = "coder"
    SUMMARY = "summary"
    MCP_EXTERNAL = "mcp_external"


class TaskStatus(Enum):
    """Status of a parallel task in the execution pipeline."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class KittyTask:
    """
    A task in the parallel execution pipeline with full metadata.

    Tasks are created during goal decomposition and executed by specialized
    agents. Each task tracks its own metrics and results.

    Attributes:
        id: Unique identifier (e.g., "task_1")
        description: What this task should accomplish
        assigned_to: Agent name responsible for execution
        status: Current execution status
        dependencies: Task IDs that must complete before this task
        result: Output from successful execution
        error: Error message if task failed
        started_at: When execution began
        completed_at: When execution finished
        latency_ms: Total execution time in milliseconds
        tokens_used: Tokens consumed during generation
        tokens_prompt: Tokens in the prompt
        cost_usd: Estimated cost in USD
        model_used: Which model actually handled the task
        fallback_used: Whether a fallback tier was used
    """
    id: str
    description: str
    assigned_to: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    latency_ms: int = 0

    # Token usage
    tokens_used: int = 0
    tokens_prompt: int = 0

    # Cost tracking
    cost_usd: float = 0.0

    # Model tracking
    model_used: str = ""
    fallback_used: bool = False

    @property
    def duration_ms(self) -> int:
        """Calculate duration from timestamps."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return self.latency_ms

    @property
    def is_ready(self) -> bool:
        """Check if task is ready to execute (no pending dependencies)."""
        return self.status == TaskStatus.PENDING

    def mark_started(self) -> None:
        """Mark task as started with current timestamp."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, result: str, model: str, tokens: int = 0) -> None:
        """Mark task as completed with result and metrics."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.result = result
        self.model_used = model
        self.tokens_used = tokens
        if self.started_at:
            self.latency_ms = self.duration_ms

    def mark_failed(self, error: str) -> None:
        """Mark task as failed with error message."""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error = error
        if self.started_at:
            self.latency_ms = self.duration_ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "tokens_prompt": self.tokens_prompt,
            "cost_usd": self.cost_usd,
            "model_used": self.model_used,
            "fallback_used": self.fallback_used,
        }


@dataclass
class AgentExecutionMetrics:
    """
    Aggregated metrics for a parallel execution run.

    Collected after all tasks complete for reporting and optimization.
    """
    goal: str
    total_time_seconds: float
    total_tokens: int
    total_cost_usd: float
    task_count: int
    completed_count: int
    failed_count: int
    parallel_batches: int
    avg_task_latency_ms: float
    max_task_latency_ms: int
    endpoints_used: List[str]
    fallback_count: int

    @classmethod
    def from_tasks(
        cls,
        goal: str,
        tasks: List[KittyTask],
        total_time: float,
        parallel_batches: int,
    ) -> "AgentExecutionMetrics":
        """Create metrics from completed task list."""
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        failed = [t for t in tasks if t.status == TaskStatus.FAILED]

        latencies = [t.latency_ms for t in tasks if t.latency_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0

        endpoints = list(set(t.model_used for t in tasks if t.model_used))
        fallbacks = sum(1 for t in tasks if t.fallback_used)

        return cls(
            goal=goal,
            total_time_seconds=round(total_time, 2),
            total_tokens=sum(t.tokens_used for t in tasks),
            total_cost_usd=sum(t.cost_usd for t in tasks),
            task_count=len(tasks),
            completed_count=len(completed),
            failed_count=len(failed),
            parallel_batches=parallel_batches,
            avg_task_latency_ms=round(avg_latency, 1),
            max_task_latency_ms=max_latency,
            endpoints_used=endpoints,
            fallback_count=fallbacks,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "goal": self.goal,
            "total_time_seconds": self.total_time_seconds,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "task_count": self.task_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "parallel_batches": self.parallel_batches,
            "avg_task_latency_ms": self.avg_task_latency_ms,
            "max_task_latency_ms": self.max_task_latency_ms,
            "endpoints_used": self.endpoints_used,
            "fallback_count": self.fallback_count,
        }
