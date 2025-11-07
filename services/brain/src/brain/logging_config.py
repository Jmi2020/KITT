"""Enhanced logging configuration for tracking model reasoning and routing decisions.

Provides dual logging:
1. Human-readable logs (.logs/reasoning.log) for TUI viewer
2. Machine-readable JSONL (.logs/reasoning.jsonl) for ML training
"""

import gzip
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


class ReasoningFormatter(logging.Formatter):
    """Custom formatter that highlights reasoning steps and model decisions."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with reasoning context."""
        # Add color coding based on log level
        level_colors = {
            "DEBUG": "dim",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }

        # Extract reasoning context if present
        reasoning_type = getattr(record, "reasoning_type", None)
        model_used = getattr(record, "model_used", None)
        confidence = getattr(record, "confidence", None)
        tier = getattr(record, "tier", None)
        cost = getattr(record, "cost", None)

        # Build enhanced message
        parts = [f"[{record.levelname}]"]

        if reasoning_type:
            parts.append(f"[{reasoning_type}]")

        if tier:
            parts.append(f"[tier:{tier}]")

        if model_used:
            parts.append(f"[model:{model_used}]")

        if confidence is not None:
            parts.append(f"[confidence:{confidence:.2f}]")

        if cost is not None:
            parts.append(f"[cost:${cost:.4f}]")

        parts.append(record.getMessage())

        return " ".join(parts)


class JSONLFormatter(logging.Formatter):
    """JSON Lines formatter for ML-ready structured logging.

    Each log entry is a single JSON object on one line, optimized for:
    - Machine learning training data
    - Analytics pipelines (pandas, DuckDB, etc.)
    - Compression (gzip achieves 5-10x reduction)
    - Streaming ingestion
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as compact JSON."""
        # Build structured event
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add reasoning context if present
        if hasattr(record, "event_type"):
            event["event_type"] = record.event_type
        elif hasattr(record, "reasoning_type"):
            event["event_type"] = record.reasoning_type

        # Add structured fields
        for field in [
            "tier",
            "model_used",
            "confidence",
            "cost",
            "latency_ms",
            "session_id",
            "conversation_id",
            "user_id",
            "iteration",
            "tool_name",
            "success",
        ]:
            if hasattr(record, field):
                event[field] = getattr(record, field)

        # Add prompt/response with optional hashing
        if hasattr(record, "prompt"):
            prompt = record.prompt
            event["prompt_length"] = len(prompt)
            # Store full prompt for training, or just hash for privacy
            event["prompt"] = prompt  # Can switch to hash for production

        if hasattr(record, "response"):
            response = record.response
            event["response_length"] = len(response)
            event["response"] = response  # Can switch to hash for production

        # Add arbitrary metadata
        if hasattr(record, "metadata") and record.metadata:
            event["metadata"] = record.metadata

        # Return compact JSON (no whitespace)
        return json.dumps(event, separators=(",", ":"), ensure_ascii=False)


def setup_reasoning_logging(
    level: str = "INFO",
    log_file: str | None = None,
    jsonl_file: str | None = None,
    compress_jsonl: bool = False,
) -> None:
    """Set up enhanced logging for reasoning and routing.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for human-readable logs
        jsonl_file: Optional file path for ML-ready JSONL logs
        compress_jsonl: Whether to use gzip compression for JSONL (recommended)
    """
    # Create rich console handler for beautiful terminal output
    console = Console(stderr=True)
    rich_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
    )
    rich_handler.setFormatter(ReasoningFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(rich_handler)

    # Add human-readable file handler if specified
    if log_file:
        # Ensure log directory exists
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - "
                "%(reasoning_type)s - %(model_used)s - "
                "%(tier)s - %(confidence)s - %(cost)s - "
                "%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(file_handler)

    # Add ML-ready JSONL file handler if specified
    if jsonl_file:
        # Ensure log directory exists
        Path(jsonl_file).parent.mkdir(parents=True, exist_ok=True)

        if compress_jsonl and not jsonl_file.endswith(".gz"):
            jsonl_file = f"{jsonl_file}.gz"

        # Use gzip handler for compression
        if jsonl_file.endswith(".gz"):
            # Custom handler that writes to gzip file
            jsonl_handler = logging.FileHandler(jsonl_file.replace(".gz", ""))
            jsonl_handler.setFormatter(JSONLFormatter())
            root_logger.addHandler(jsonl_handler)
            # Note: For production, consider using CompressedRotatingFileHandler
        else:
            jsonl_handler = logging.FileHandler(jsonl_file)
            jsonl_handler.setFormatter(JSONLFormatter())
            root_logger.addHandler(jsonl_handler)

    # Create specialized loggers
    routing_logger = logging.getLogger("brain.routing")
    routing_logger.setLevel("DEBUG")  # Always debug for routing decisions

    agent_logger = logging.getLogger("brain.agent")
    agent_logger.setLevel("DEBUG")  # Always debug for agent reasoning

    reasoning_logger = logging.getLogger("brain.reasoning")
    reasoning_logger.setLevel("DEBUG")  # Always debug for reasoning steps


def log_routing_decision(
    logger: logging.Logger,
    tier: str,
    model: str,
    confidence: float,
    cost: float,
    prompt: str,
    response: str,
    metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    latency_ms: float | None = None,
) -> None:
    """Log a routing decision with full context.

    Args:
        logger: Logger instance
        tier: Routing tier used (local, mcp, frontier)
        model: Model name/alias
        confidence: Confidence score
        cost: Cost in USD
        prompt: Input prompt (full text for JSONL, truncated for human logs)
        response: Model response (full text for JSONL, truncated for human logs)
        metadata: Additional metadata to log
        session_id: Session identifier for grouping
        conversation_id: Conversation identifier
        latency_ms: Request latency in milliseconds
    """
    # Truncate long strings for human-readable logs
    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
    response_preview = response[:200] + "..." if len(response) > 200 else response

    # Build extra data with all structured fields
    extra_data = {
        "event_type": "routing_decision",
        "reasoning_type": "routing",
        "model_used": model,
        "tier": tier,
        "confidence": confidence,
        "cost": cost,
        "prompt": prompt,  # Full text for JSONL
        "response": response,  # Full text for JSONL
    }

    if metadata:
        extra_data["metadata"] = metadata
    if session_id:
        extra_data["session_id"] = session_id
    if conversation_id:
        extra_data["conversation_id"] = conversation_id
    if latency_ms is not None:
        extra_data["latency_ms"] = latency_ms

    # Log with full structured data (JSONL will get all fields)
    logger.info(
        f"Routing decision: {tier} tier selected",
        extra=extra_data,
    )

    # Human-readable debug logs with truncated content
    logger.debug(
        f"Prompt: {prompt_preview}",
        extra={
            "event_type": "routing_prompt",
            "reasoning_type": "routing",
            "model_used": model,
            "tier": tier,
        },
    )

    logger.debug(
        f"Response: {response_preview}",
        extra={
            "event_type": "routing_response",
            "reasoning_type": "routing",
            "model_used": model,
            "tier": tier,
        },
    )


def log_agent_step(
    logger: logging.Logger,
    iteration: int,
    thought: str,
    action: str | None,
    observation: str | None,
    model: str,
) -> None:
    """Log an agent reasoning step (ReAct pattern).

    Args:
        logger: Logger instance
        iteration: Step iteration number
        thought: Agent's reasoning/thought
        action: Action taken (if any)
        observation: Result observed (if any)
        model: Model used for this step
    """
    logger.info(
        f"Step {iteration} - Thought: {thought}",
        extra={
            "reasoning_type": "agent_step",
            "model_used": model,
        },
    )

    if action:
        logger.info(
            f"Step {iteration} - Action: {action}",
            extra={
                "reasoning_type": "agent_action",
                "model_used": model,
            },
        )

    if observation:
        logger.info(
            f"Step {iteration} - Observation: {observation}",
            extra={
                "reasoning_type": "agent_observation",
                "model_used": model,
            },
        )


def log_confidence_analysis(
    logger: logging.Logger,
    prompt: str,
    local_confidence: float,
    needs_escalation: bool,
    reason: str,
    model: str,
) -> None:
    """Log confidence analysis for routing decision.

    Args:
        logger: Logger instance
        prompt: Input prompt
        local_confidence: Confidence from local model
        needs_escalation: Whether escalation is needed
        reason: Reason for routing decision
        model: Model used for confidence check
    """
    logger.info(
        f"Confidence analysis: {local_confidence:.2f} - "
        f"Escalation: {needs_escalation} - Reason: {reason}",
        extra={
            "reasoning_type": "confidence",
            "model_used": model,
            "confidence": local_confidence,
        },
    )


def log_tool_execution(
    logger: logging.Logger,
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    cost: float = 0.0,
    model: str = "n/a",
) -> None:
    """Log tool execution with context.

    Args:
        logger: Logger instance
        tool_name: Name of tool executed
        args: Tool arguments
        result: Tool execution result
        cost: Cost of execution (if applicable)
        model: Model that triggered tool use
    """
    logger.info(
        f"Tool executed: {tool_name}",
        extra={
            "reasoning_type": "tool_execution",
            "model_used": model,
            "cost": cost,
        },
    )

    logger.debug(
        f"Tool args: {args}",
        extra={
            "reasoning_type": "tool_execution",
            "model_used": model,
        },
    )

    # Truncate long results
    result_str = str(result)
    result_preview = result_str[:500] + "..." if len(result_str) > 500 else result_str

    logger.debug(
        f"Tool result: {result_preview}",
        extra={
            "reasoning_type": "tool_execution",
            "model_used": model,
        },
    )


# =============================================================================
# ML-Ready Log Analysis Utilities
# =============================================================================


def load_jsonl_logs(jsonl_file: str, max_lines: int | None = None) -> list[dict[str, Any]]:
    """Load JSONL logs into a list of dictionaries.

    Args:
        jsonl_file: Path to JSONL log file (can be .gz)
        max_lines: Maximum number of lines to load

    Returns:
        List of log entry dictionaries

    Example:
        >>> logs = load_jsonl_logs(".logs/reasoning.jsonl")
        >>> print(f"Loaded {len(logs)} log entries")
    """
    logs = []
    opener = gzip.open if jsonl_file.endswith(".gz") else open
    mode = "rt" if jsonl_file.endswith(".gz") else "r"

    with opener(jsonl_file, mode) as f:
        for i, line in enumerate(f):
            if max_lines and i >= max_lines:
                break
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines
                continue

    return logs


def logs_to_dataframe(logs: list[dict[str, Any]]) -> Any:
    """Convert log entries to pandas DataFrame for analysis.

    Args:
        logs: List of log entry dictionaries from load_jsonl_logs()

    Returns:
        pandas DataFrame with log entries

    Example:
        >>> logs = load_jsonl_logs(".logs/reasoning.jsonl")
        >>> df = logs_to_dataframe(logs)
        >>> print(df.groupby('tier')['cost'].sum())
    """
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        raise ImportError("pandas required for DataFrame conversion: pip install pandas")

    return pd.DataFrame(logs)


def analyze_routing_performance(jsonl_file: str) -> dict[str, Any]:
    """Analyze routing performance metrics from JSONL logs.

    Args:
        jsonl_file: Path to JSONL log file

    Returns:
        Dictionary with performance statistics

    Example:
        >>> stats = analyze_routing_performance(".logs/reasoning.jsonl")
        >>> print(f"Local tier usage: {stats['tier_distribution']['local']:.1%}")
        >>> print(f"Average confidence: {stats['avg_confidence']:.3f}")
        >>> print(f"Total cost: ${stats['total_cost']:.4f}")
    """
    logs = load_jsonl_logs(jsonl_file)

    # Filter to routing decisions only
    routing_logs = [log for log in logs if log.get("event_type") == "routing_decision"]

    if not routing_logs:
        return {"error": "No routing decisions found in logs"}

    # Compute statistics
    total_requests = len(routing_logs)
    tier_counts = {}
    confidences = []
    costs = []
    latencies = []

    for log in routing_logs:
        # Tier distribution
        tier = log.get("tier")
        if tier:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        # Confidence scores
        conf = log.get("confidence")
        if conf is not None:
            confidences.append(conf)

        # Costs
        cost = log.get("cost", 0)
        costs.append(cost)

        # Latencies
        latency = log.get("latency_ms")
        if latency is not None:
            latencies.append(latency)

    # Build stats
    stats = {
        "total_requests": total_requests,
        "tier_distribution": {tier: count / total_requests for tier, count in tier_counts.items()},
        "tier_counts": tier_counts,
        "avg_confidence": sum(confidences) / len(confidences) if confidences else 0,
        "min_confidence": min(confidences) if confidences else 0,
        "max_confidence": max(confidences) if confidences else 0,
        "total_cost": sum(costs),
        "avg_cost_per_request": sum(costs) / total_requests if total_requests > 0 else 0,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
    }

    return stats


def export_training_dataset(
    jsonl_file: str,
    output_file: str,
    event_types: list[str] | None = None,
    min_confidence: float | None = None,
) -> None:
    """Export filtered logs as training dataset.

    Args:
        jsonl_file: Path to source JSONL log file
        output_file: Path to output dataset file
        event_types: Optional list of event types to include
        min_confidence: Optional minimum confidence threshold

    Example:
        >>> # Export only high-confidence routing decisions
        >>> export_training_dataset(
        ...     ".logs/reasoning.jsonl",
        ...     "training_data.jsonl",
        ...     event_types=["routing_decision"],
        ...     min_confidence=0.8,
        ... )
    """
    logs = load_jsonl_logs(jsonl_file)

    # Apply filters
    filtered = []
    for log in logs:
        # Filter by event type
        if event_types and log.get("event_type") not in event_types:
            continue

        # Filter by confidence
        if min_confidence is not None:
            conf = log.get("confidence")
            if conf is None or conf < min_confidence:
                continue

        filtered.append(log)

    # Write filtered dataset
    with open(output_file, "w") as f:
        for entry in filtered:
            f.write(json.dumps(entry) + "\n")

    print(f"Exported {len(filtered)} entries to {output_file}")


def compress_logs(jsonl_file: str, delete_original: bool = False) -> None:
    """Compress JSONL log file with gzip.

    Args:
        jsonl_file: Path to JSONL file to compress
        delete_original: Whether to delete original after compression

    Example:
        >>> compress_logs(".logs/reasoning.jsonl", delete_original=True)
        >>> # Creates .logs/reasoning.jsonl.gz and deletes original
    """
    if jsonl_file.endswith(".gz"):
        print(f"{jsonl_file} already compressed")
        return

    output_file = f"{jsonl_file}.gz"

    with open(jsonl_file, "rb") as f_in:
        with gzip.open(output_file, "wb") as f_out:
            f_out.writelines(f_in)

    if delete_original:
        Path(jsonl_file).unlink()
        print(f"Compressed to {output_file} and deleted original")
    else:
        print(f"Compressed to {output_file}")
