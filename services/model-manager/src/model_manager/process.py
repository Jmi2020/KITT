# noqa: D401
"""Process management for llama.cpp server."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import psutil

from .models import ServerConfig, ServerStatus

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_PID_FILE = Path.home() / ".kitty" / "llamacpp.pid"
DEFAULT_LOG_FILE = Path.home() / ".kitty" / "logs" / "llamacpp.log"


class ProcessError(Exception):
    """Base exception for process management errors."""

    pass


class ProcessManager:
    """Manages llama.cpp server process lifecycle."""

    def __init__(
        self,
        pid_file: Optional[Path] = None,
        log_file: Optional[Path] = None,
        startup_timeout: int = 120,
        shutdown_timeout: int = 10,
    ) -> None:
        """Initialize process manager.

        Args:
            pid_file: Path to PID file (defaults to ~/.kitty/llamacpp.pid)
            log_file: Path to log file (defaults to ~/.kitty/logs/llamacpp.log)
            startup_timeout: Maximum seconds to wait for startup
            shutdown_timeout: Maximum seconds to wait for graceful shutdown
        """
        self.pid_file = pid_file or DEFAULT_PID_FILE
        self.log_file = log_file or DEFAULT_LOG_FILE
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout

        # Ensure directories exist
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self._process: Optional[subprocess.Popen] = None

    def start(self, config: ServerConfig) -> bool:
        """Start llama.cpp server with given configuration.

        Args:
            config: Server configuration

        Returns:
            True if server started successfully

        Raises:
            ProcessError: If server is already running or fails to start
        """
        # Check if already running
        if self.is_running():
            pid = self._read_pid()
            raise ProcessError(f"Server already running with PID {pid}")

        # Generate command
        cmd = config.to_command()
        logger.info(f"Starting llama.cpp server: {' '.join(cmd)}")

        try:
            # Open log file for writing
            log_handle = open(self.log_file, "a")

            # Start process
            self._process = subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # Detach from parent
            )

            # Write PID file
            self._write_pid(self._process.pid)

            logger.info(f"Server started with PID {self._process.pid}")
            return True

        except FileNotFoundError:
            raise ProcessError(f"Binary not found: {config.binary}")
        except PermissionError:
            raise ProcessError(f"Permission denied: {config.binary}")
        except Exception as e:
            raise ProcessError(f"Failed to start server: {e}")

    def stop(self, force: bool = False) -> bool:
        """Stop running llama.cpp server.

        Args:
            force: If True, use SIGKILL immediately. If False, try SIGTERM first.

        Returns:
            True if server stopped successfully

        Raises:
            ProcessError: If server is not running or fails to stop
        """
        if not self.is_running():
            logger.warning("Server is not running")
            return False

        pid = self._read_pid()
        logger.info(f"Stopping server with PID {pid}")

        try:
            process = psutil.Process(pid)

            if force:
                # Force kill immediately
                process.kill()
                logger.info(f"Sent SIGKILL to PID {pid}")
            else:
                # Try graceful shutdown first
                process.terminate()
                logger.info(f"Sent SIGTERM to PID {pid}")

                # Wait for graceful shutdown
                try:
                    process.wait(timeout=self.shutdown_timeout)
                    logger.info(f"Process {pid} exited gracefully")
                except psutil.TimeoutExpired:
                    logger.warning(
                        f"Process {pid} did not exit after {self.shutdown_timeout}s, sending SIGKILL"
                    )
                    process.kill()
                    process.wait(timeout=5)

            # Clean up PID file
            self._cleanup_pid()
            self._process = None

            logger.info(f"Server stopped successfully")
            return True

        except psutil.NoSuchProcess:
            logger.warning(f"Process {pid} does not exist, cleaning up PID file")
            self._cleanup_pid()
            return False
        except Exception as e:
            raise ProcessError(f"Failed to stop server: {e}")

    def restart(self, config: ServerConfig, force: bool = False) -> bool:
        """Restart llama.cpp server with new configuration.

        Args:
            config: New server configuration
            force: If True, force kill existing process

        Returns:
            True if server restarted successfully
        """
        logger.info("Restarting server")

        # Stop existing server if running
        if self.is_running():
            self.stop(force=force)

        # Wait a moment for port to be released
        time.sleep(1)

        # Start with new config
        return self.start(config)

    def is_running(self) -> bool:
        """Check if server is currently running.

        Returns:
            True if server process is alive
        """
        pid = self._read_pid()
        if pid is None:
            return False

        try:
            process = psutil.Process(pid)
            # Check if it's actually a llama-server process
            cmdline = " ".join(process.cmdline())
            return "llama-server" in cmdline or "llama.cpp" in cmdline
        except psutil.NoSuchProcess:
            # PID file exists but process doesn't - clean up
            self._cleanup_pid()
            return False

    def get_status(self) -> ServerStatus:
        """Get current server status.

        Returns:
            ServerStatus enum value
        """
        if not self.is_running():
            return ServerStatus.STOPPED

        pid = self._read_pid()
        if pid is None:
            return ServerStatus.STOPPED

        try:
            process = psutil.Process(pid)
            # Check process state
            if process.status() == psutil.STATUS_ZOMBIE:
                return ServerStatus.CRASHED
            return ServerStatus.READY  # Will be refined by health checker

        except psutil.NoSuchProcess:
            return ServerStatus.CRASHED

    def get_pid(self) -> Optional[int]:
        """Get PID of running server.

        Returns:
            PID or None if not running
        """
        return self._read_pid()

    def get_process_info(self) -> Optional[dict]:
        """Get detailed process information.

        Returns:
            Dictionary with process info or None if not running
        """
        pid = self._read_pid()
        if pid is None:
            return None

        try:
            process = psutil.Process(pid)
            return {
                "pid": pid,
                "status": process.status(),
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_mb": process.memory_info().rss / (1024 * 1024),
                "num_threads": process.num_threads(),
                "create_time": process.create_time(),
                "cmdline": " ".join(process.cmdline()),
            }
        except psutil.NoSuchProcess:
            return None

    def get_log_tail(self, lines: int = 50) -> List[str]:
        """Get last N lines from server log.

        Args:
            lines: Number of lines to retrieve

        Returns:
            List of log lines
        """
        if not self.log_file.exists():
            return []

        try:
            with open(self.log_file, "r") as f:
                return f.readlines()[-lines:]
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return []

    def rotate_logs(self, max_size_mb: int = 100) -> None:
        """Rotate log file if it exceeds size limit.

        Args:
            max_size_mb: Maximum log file size in MB
        """
        if not self.log_file.exists():
            return

        size_mb = self.log_file.stat().st_size / (1024 * 1024)
        if size_mb > max_size_mb:
            # Move to .old
            old_log = self.log_file.with_suffix(".log.old")
            if old_log.exists():
                old_log.unlink()
            self.log_file.rename(old_log)
            logger.info(f"Rotated log file (was {size_mb:.1f} MB)")

    def _read_pid(self) -> Optional[int]:
        """Read PID from PID file.

        Returns:
            PID or None if file doesn't exist
        """
        if not self.pid_file.exists():
            return None

        try:
            pid_str = self.pid_file.read_text().strip()
            return int(pid_str)
        except (ValueError, IOError) as e:
            logger.warning(f"Invalid PID file: {e}")
            return None

    def _write_pid(self, pid: int) -> None:
        """Write PID to PID file.

        Args:
            pid: Process ID to write
        """
        try:
            self.pid_file.write_text(str(pid))
            logger.debug(f"Wrote PID {pid} to {self.pid_file}")
        except IOError as e:
            logger.error(f"Failed to write PID file: {e}")

    def _cleanup_pid(self) -> None:
        """Remove PID file."""
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
                logger.debug(f"Removed PID file {self.pid_file}")
            except IOError as e:
                logger.error(f"Failed to remove PID file: {e}")


def get_process_manager(
    pid_file: Optional[Path] = None,
    log_file: Optional[Path] = None,
) -> ProcessManager:
    """Get process manager instance.

    Args:
        pid_file: Optional custom PID file path
        log_file: Optional custom log file path

    Returns:
        ProcessManager instance
    """
    return ProcessManager(pid_file=pid_file, log_file=log_file)


__all__ = [
    "ProcessManager",
    "ProcessError",
    "get_process_manager",
]
