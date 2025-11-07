# noqa: D401
"""Supervisor for llama.cpp server with auto-restart capabilities."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import ConfigManager
from .health import HealthCheckResult, HealthChecker, sync_wait_for_ready
from .models import ServerConfig, ServerStatus
from .process import ProcessError, ProcessManager

logger = logging.getLogger(__name__)


@dataclass
class SupervisorState:
    """Current state of the supervisor."""

    status: ServerStatus
    config: ServerConfig
    pid: Optional[int] = None
    uptime_seconds: float = 0.0
    restart_count: int = 0
    last_restart: Optional[datetime] = None
    last_health_check: Optional[HealthCheckResult] = None
    error: Optional[str] = None


class SupervisorError(Exception):
    """Exception raised by supervisor."""

    pass


class ServerSupervisor:
    """Supervises llama.cpp server with auto-restart on failure."""

    def __init__(
        self,
        config_manager: ConfigManager,
        process_manager: ProcessManager,
        max_restart_attempts: int = 3,
        restart_delay: float = 5.0,
        backoff_factor: float = 2.0,
        max_restart_delay: float = 60.0,
    ) -> None:
        """Initialize supervisor.

        Args:
            config_manager: Configuration manager instance
            process_manager: Process manager instance
            max_restart_attempts: Maximum consecutive restart attempts
            restart_delay: Initial delay before restart in seconds
            backoff_factor: Exponential backoff multiplier
            max_restart_delay: Maximum delay between restarts
        """
        self.config_manager = config_manager
        self.process_manager = process_manager
        self.max_restart_attempts = max_restart_attempts
        self.restart_delay = restart_delay
        self.backoff_factor = backoff_factor
        self.max_restart_delay = max_restart_delay

        self._config: Optional[ServerConfig] = None
        self._restart_count = 0
        self._start_time: Optional[datetime] = None
        self._on_status_change: Optional[Callable[[SupervisorState], None]] = None

    def set_status_callback(self, callback: Callable[[SupervisorState], None]) -> None:
        """Set callback for status changes.

        Args:
            callback: Function to call on status change
        """
        self._on_status_change = callback

    def start(
        self,
        config: Optional[ServerConfig] = None,
        wait_for_ready: bool = True,
    ) -> SupervisorState:
        """Start server with supervision.

        Args:
            config: Server configuration (loads from .env if not provided)
            wait_for_ready: If True, wait for server to be ready before returning

        Returns:
            SupervisorState after startup

        Raises:
            SupervisorError: If startup fails
        """
        # Load config if not provided
        if config is None:
            config = self.config_manager.load()
        self._config = config

        logger.info(f"Starting server with model: {config.primary_model}")

        # Start process
        try:
            self.process_manager.start(config)
            self._start_time = datetime.now()
            self._restart_count = 0
        except ProcessError as e:
            raise SupervisorError(f"Failed to start server: {e}")

        state = self._get_state()
        self._notify_status_change(state)

        # Wait for ready if requested
        if wait_for_ready:
            logger.info("Waiting for server to be ready...")
            try:
                result = sync_wait_for_ready(config.endpoint, max_retries=120)
                state = self._get_state()
                state.last_health_check = result
                state.status = ServerStatus.READY
                logger.info("Server is ready")
            except Exception as e:
                logger.error(f"Server failed to become ready: {e}")
                state.status = ServerStatus.FAILED
                state.error = str(e)

            self._notify_status_change(state)

        return state

    def stop(self, force: bool = False) -> SupervisorState:
        """Stop supervised server.

        Args:
            force: If True, force kill the process

        Returns:
            SupervisorState after stopping
        """
        logger.info("Stopping server")

        try:
            self.process_manager.stop(force=force)
            self._start_time = None
        except ProcessError as e:
            logger.error(f"Error stopping server: {e}")

        state = self._get_state()
        self._notify_status_change(state)
        return state

    def restart(
        self,
        config: Optional[ServerConfig] = None,
        force: bool = False,
        wait_for_ready: bool = True,
    ) -> SupervisorState:
        """Restart server with optional new configuration.

        Args:
            config: New configuration (uses current if not provided)
            force: If True, force kill existing process
            wait_for_ready: If True, wait for ready after restart

        Returns:
            SupervisorState after restart
        """
        logger.info("Restarting server")

        # Use current config if not provided
        if config is None:
            config = self._config or self.config_manager.load()

        # Stop if running
        if self.process_manager.is_running():
            self.stop(force=force)

        # Start with new config
        return self.start(config=config, wait_for_ready=wait_for_ready)

    def auto_restart(
        self,
        wait_for_ready: bool = True,
    ) -> SupervisorState:
        """Attempt automatic restart with exponential backoff.

        Args:
            wait_for_ready: If True, wait for ready after restart

        Returns:
            SupervisorState after restart

        Raises:
            SupervisorError: If max restart attempts exceeded
        """
        self._restart_count += 1

        if self._restart_count > self.max_restart_attempts:
            raise SupervisorError(
                f"Max restart attempts ({self.max_restart_attempts}) exceeded"
            )

        # Calculate delay with exponential backoff
        delay = min(
            self.restart_delay * (self.backoff_factor ** (self._restart_count - 1)),
            self.max_restart_delay,
        )

        logger.warning(
            f"Auto-restart attempt {self._restart_count}/"
            f"{self.max_restart_attempts} (waiting {delay:.1f}s)"
        )

        # Wait before restarting
        import time

        time.sleep(delay)

        # Attempt restart
        try:
            state = self.restart(wait_for_ready=wait_for_ready)
            if state.status == ServerStatus.READY:
                # Reset restart counter on success
                self._restart_count = 0
            return state
        except Exception as e:
            logger.error(f"Auto-restart failed: {e}")
            state = self._get_state()
            state.status = ServerStatus.FAILED
            state.error = str(e)
            self._notify_status_change(state)
            raise SupervisorError(f"Auto-restart failed: {e}")

    def switch_model(
        self,
        model_path: str,
        alias: Optional[str] = None,
        wait_for_ready: bool = True,
    ) -> SupervisorState:
        """Switch to a different model (hot-swap).

        Args:
            model_path: Relative path to model from models_dir
            alias: Optional model alias
            wait_for_ready: If True, wait for ready after switch

        Returns:
            SupervisorState after switch
        """
        logger.info(f"Switching to model: {model_path}")

        # Update config
        self.config_manager.update_model(model_path, alias)
        config = self.config_manager.load()

        # Restart with new config
        return self.restart(config=config, wait_for_ready=wait_for_ready)

    def get_state(self) -> SupervisorState:
        """Get current supervisor state.

        Returns:
            SupervisorState with current status
        """
        return self._get_state()

    def check_health(self) -> SupervisorState:
        """Perform health check and update state.

        Returns:
            SupervisorState with health check results
        """
        if not self._config:
            state = self._get_state()
            state.status = ServerStatus.STOPPED
            return state

        try:
            from .health import sync_check_health

            result = sync_check_health(self._config.endpoint, timeout=5)
            state = self._get_state()
            state.last_health_check = result
            state.status = result.status
            self._notify_status_change(state)
            return state
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            state = self._get_state()
            state.status = ServerStatus.FAILED
            state.error = str(e)
            self._notify_status_change(state)
            return state

    def _get_state(self) -> SupervisorState:
        """Get current state.

        Returns:
            SupervisorState
        """
        status = self.process_manager.get_status()
        pid = self.process_manager.get_pid()

        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()

        return SupervisorState(
            status=status,
            config=self._config or self.config_manager.load(),
            pid=pid,
            uptime_seconds=uptime,
            restart_count=self._restart_count,
            last_restart=self._start_time,
        )

    def _notify_status_change(self, state: SupervisorState) -> None:
        """Notify status callback.

        Args:
            state: Current state
        """
        if self._on_status_change:
            try:
                self._on_status_change(state)
            except Exception as e:
                logger.error(f"Status callback error: {e}")


def get_supervisor(
    env_path: Optional[Path] = None,
    pid_file: Optional[Path] = None,
    log_file: Optional[Path] = None,
) -> ServerSupervisor:
    """Get server supervisor instance.

    Args:
        env_path: Optional path to .env file
        pid_file: Optional PID file path
        log_file: Optional log file path

    Returns:
        ServerSupervisor instance
    """
    from .config import ConfigManager
    from .process import ProcessManager

    config_manager = ConfigManager(env_path)
    process_manager = ProcessManager(pid_file=pid_file, log_file=log_file)

    return ServerSupervisor(
        config_manager=config_manager,
        process_manager=process_manager,
    )


__all__ = [
    "ServerSupervisor",
    "SupervisorState",
    "SupervisorError",
    "get_supervisor",
]
