"""Centralised logging configuration with JSON output."""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict

import structlog

DEFAULT_LOG_LEVEL = "INFO"


def _configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(DEFAULT_LOG_LEVEL)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_logging(level: str = DEFAULT_LOG_LEVEL) -> None:
    """Initialise stdlib + structlog JSON logging."""

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    _configure_structlog()


def get_logger(name: str, **initial_values: Dict[str, Any]) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger."""

    configure_logging()
    logger = structlog.get_logger(name)
    if initial_values:
        return logger.bind(**initial_values)
    return logger


__all__ = ["configure_logging", "get_logger"]
