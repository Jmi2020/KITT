"""JSONL audit logging for command execution."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pythonjsonlogger import jsonlogger


class AuditLogger:
    """Structured JSONL audit logger for command execution."""

    def __init__(self, log_path: str = "/var/log/kitty/broker-audit.jsonl"):
        """Initialize audit logger.

        Args:
            log_path: Path to JSONL audit log file
        """
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create logger
        self.logger = logging.getLogger("broker.audit")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Add JSONL file handler
        handler = logging.FileHandler(str(self.log_path))
        formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(level)s %(message)s %(command)s %(user)s %(success)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def log_execution(
        self,
        command_name: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Log command execution to JSONL audit log.

        Args:
            command_name: Name of executed command
            args: Command arguments
            result: Execution result
            user_id: User who initiated command
            conversation_id: Conversation ID for traceability
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "message": "Command executed",
            "command": command_name,
            "args": args,
            "result": {
                "success": result.get("success"),
                "exit_code": result.get("exit_code"),
                "timeout": result.get("timeout_exceeded"),
                "error": result.get("error"),
            },
            "user": user_id or "unknown",
            "conversation_id": conversation_id,
            "success": result.get("success"),
        }

        # Log as structured JSON
        self.logger.info(
            entry["message"],
            extra={
                "timestamp": entry["timestamp"],
                "command": command_name,
                "user": user_id,
                "success": result.get("success"),
            },
        )

        # Also write raw JSON to file for guaranteed JSONL format
        with self.log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")


__all__ = ["AuditLogger"]
