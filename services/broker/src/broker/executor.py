"""Subprocess executor with privilege dropping and timeout enforcement."""

from __future__ import annotations

import asyncio
import os
import pwd
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .config import CommandDefinition


@dataclass
class ExecutionResult:
    """Result of command execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: str
    timeout_exceeded: bool = False
    error: Optional[str] = None


class CommandExecutor:
    """Execute commands with privilege dropping and timeout enforcement."""

    def __init__(
        self, service_user: str = "kitty-runner", enable_privilege_drop: bool = True
    ):
        """Initialize executor.

        Args:
            service_user: User to run commands as (default: kitty-runner)
            enable_privilege_drop: Whether to drop privileges (disable for testing)
        """
        self.service_user = service_user
        self.enable_privilege_drop = enable_privilege_drop
        self._uid: Optional[int] = None
        self._gid: Optional[int] = None

        if self.enable_privilege_drop:
            try:
                pw = pwd.getpwnam(service_user)
                self._uid = pw.pw_uid
                self._gid = pw.pw_gid
            except KeyError:
                raise ValueError(
                    f"Service user '{service_user}' not found. "
                    "Run: sudo dscl . -create /Users/kitty-runner UserShell /usr/bin/false"
                )

    def _demote_privileges(self) -> None:
        """Drop privileges to service user (for subprocess preexec_fn)."""
        if self.enable_privilege_drop and self._gid and self._uid:
            os.setgid(self._gid)
            os.setuid(self._uid)

    async def execute(
        self,
        command_def: CommandDefinition,
        args: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute command with validation, privilege dropping, and timeout.

        Args:
            command_def: Command definition from allow-list
            args: Arguments to pass to command
            timeout: Override timeout from command definition

        Returns:
            ExecutionResult with output and status
        """
        # Validate arguments against JSON Schema
        try:
            command_def.validate_args(args)
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                command=command_def.name,
                error=f"Argument validation failed: {e}",
            )

        # Build command list
        cmd = command_def.build_command(args)
        timeout_sec = timeout or command_def.timeout

        # Execute with privilege drop
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._demote_privileges
                if self.enable_privilege_drop
                else None,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_sec
            )

            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                command=" ".join(cmd),
            )

        except asyncio.TimeoutError:
            # Kill process on timeout
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass

            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                command=" ".join(cmd),
                timeout_exceeded=True,
                error=f"Command exceeded timeout of {timeout_sec}s",
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                command=" ".join(cmd),
                error=f"Execution failed: {e}",
            )


__all__ = ["CommandExecutor", "ExecutionResult"]
