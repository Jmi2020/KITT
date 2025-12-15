"""Native Process Starter for KITTY ServiceManager.

Starts native Mac processes like the Voice service.
Uses startup scripts and tracks PIDs.
"""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Dict, Optional

from .health_checker import HealthChecker
from .types import ServiceDefinition, ServiceType

logger = logging.getLogger(__name__)

# Base path for KITTY project
_KITTY_ROOT = Path(__file__).parents[6]
_LOG_DIR = _KITTY_ROOT / ".logs"


class NativeStarter:
    """Starts and manages native Mac processes.

    Uses existing startup scripts (e.g., start-voice-service.sh)
    and tracks process PIDs for management.
    """

    def __init__(self, health_checker: Optional[HealthChecker] = None):
        """Initialize the native starter.

        Args:
            health_checker: HealthChecker for waiting on service health.
        """
        self._health_checker = health_checker
        self._processes: Dict[str, asyncio.subprocess.Process] = {}

    async def start_service(
        self,
        service: ServiceDefinition,
        wait_for_health: bool = True,
    ) -> bool:
        """Start a native process service.

        Args:
            service: The service definition to start.
            wait_for_health: Whether to wait for health check to pass.

        Returns:
            True if service started successfully, False otherwise.
        """
        if service.service_type != ServiceType.NATIVE_PROCESS:
            logger.error(f"Service {service.name} is not a native process")
            return False

        if not service.start_script:
            logger.error(f"No start script defined for {service.name}")
            return False

        script_path = Path(service.start_script)
        if not script_path.exists():
            logger.error(f"Start script not found: {script_path}")
            return False

        # Check if already running by health check
        if self._health_checker:
            health = await self._health_checker.check_health(service)
            if health.is_healthy:
                logger.info(f"Service {service.name} is already running")
                return True

        logger.info(f"Starting {service.name} via {script_path}")

        try:
            # Run the startup script
            # Scripts are expected to handle daemonization and PID files
            proc = await asyncio.create_subprocess_exec(
                "bash",
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_KITTY_ROOT),
            )

            # Wait for script to complete (it daemonizes the service)
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=30.0,
            )

            if proc.returncode != 0:
                logger.error(
                    f"Start script failed for {service.name}: "
                    f"rc={proc.returncode}, stderr={stderr.decode()}"
                )
                return False

            logger.info(f"Start script completed for {service.name}")

            # Wait for health if requested
            if wait_for_health and self._health_checker:
                return await self._wait_for_health(service)

            return True

        except asyncio.TimeoutError:
            logger.error(f"Timeout starting {service.name}")
            return False
        except Exception as e:
            logger.exception(f"Error starting {service.name}: {e}")
            return False

    async def _wait_for_health(
        self,
        service: ServiceDefinition,
    ) -> bool:
        """Wait for a service to become healthy.

        Args:
            service: The service to wait for.

        Returns:
            True if service became healthy, False on timeout.
        """
        timeout = service.startup_timeout_seconds
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Waiting up to {timeout}s for {service.name} to become healthy")

        while asyncio.get_event_loop().time() - start_time < timeout:
            health = await self._health_checker.check_health(service)
            if health.is_healthy:
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(f"Service {service.name} is healthy after {elapsed:.1f}s")
                return True
            await asyncio.sleep(1.0)

        logger.error(f"Service {service.name} did not become healthy within {timeout}s")
        return False

    async def stop_service(
        self,
        service: ServiceDefinition,
        graceful_timeout: float = 10.0,
    ) -> bool:
        """Stop a native process service.

        Uses the PID file created by the startup script.

        Args:
            service: The service to stop.
            graceful_timeout: Seconds to wait for graceful shutdown.

        Returns:
            True if service stopped, False otherwise.
        """
        if service.service_type != ServiceType.NATIVE_PROCESS:
            logger.error(f"Service {service.name} is not a native process")
            return False

        # Look for PID file
        pid_file = _LOG_DIR / f"{service.name}-service.pid"
        if not pid_file.exists():
            logger.warning(f"No PID file found for {service.name}")
            return True  # Consider it stopped

        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, IOError) as e:
            logger.error(f"Cannot read PID file for {service.name}: {e}")
            return False

        logger.info(f"Stopping {service.name} (PID {pid})")

        try:
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            for _ in range(int(graceful_timeout)):
                await asyncio.sleep(1.0)
                try:
                    os.kill(pid, 0)  # Check if still running
                except ProcessLookupError:
                    logger.info(f"Service {service.name} stopped gracefully")
                    pid_file.unlink(missing_ok=True)
                    return True

            # Force kill if still running
            logger.warning(f"Force killing {service.name}")
            os.kill(pid, signal.SIGKILL)
            pid_file.unlink(missing_ok=True)
            return True

        except ProcessLookupError:
            logger.info(f"Service {service.name} was not running")
            pid_file.unlink(missing_ok=True)
            return True
        except Exception as e:
            logger.exception(f"Error stopping {service.name}: {e}")
            return False

    def get_pid(self, service: ServiceDefinition) -> Optional[int]:
        """Get the PID of a running service.

        Args:
            service: The service to get PID for.

        Returns:
            PID if running, None otherwise.
        """
        pid_file = _LOG_DIR / f"{service.name}-service.pid"
        if not pid_file.exists():
            return None

        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is still running
            os.kill(pid, 0)
            return pid
        except (ValueError, IOError, ProcessLookupError):
            return None

    def is_running(self, service: ServiceDefinition) -> bool:
        """Check if a service process is running.

        Args:
            service: The service to check.

        Returns:
            True if process is running.
        """
        return self.get_pid(service) is not None
