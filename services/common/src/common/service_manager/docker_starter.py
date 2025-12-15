"""Docker Service Starter for KITTY ServiceManager.

Starts Docker Compose services using the docker compose CLI.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from .health_checker import HealthChecker
from .types import ServiceDefinition, ServiceType

logger = logging.getLogger(__name__)

# Base path for KITTY project
_KITTY_ROOT = Path(__file__).parents[6]
_COMPOSE_FILE = _KITTY_ROOT / "infra/compose/docker-compose.yml"


class DockerStarter:
    """Starts and manages Docker Compose services.

    Uses docker compose CLI to start, stop, and inspect services.
    """

    def __init__(
        self,
        health_checker: Optional[HealthChecker] = None,
        compose_file: Optional[Path] = None,
    ):
        """Initialize the Docker starter.

        Args:
            health_checker: HealthChecker for waiting on service health.
            compose_file: Path to docker-compose.yml file.
        """
        self._health_checker = health_checker
        self._compose_file = compose_file or _COMPOSE_FILE

    async def start_service(
        self,
        service: ServiceDefinition,
        wait_for_health: bool = True,
    ) -> bool:
        """Start a Docker Compose service.

        Args:
            service: The service definition to start.
            wait_for_health: Whether to wait for health check to pass.

        Returns:
            True if service started successfully, False otherwise.
        """
        if service.service_type not in (ServiceType.DOCKER_SERVICE, ServiceType.DOCKER_INFRA):
            logger.error(f"Service {service.name} is not a Docker service")
            return False

        docker_name = service.docker_service_name or service.name

        # Check if already running by health check
        if self._health_checker:
            health = await self._health_checker.check_health(service)
            if health.is_healthy:
                logger.info(f"Service {service.name} is already running")
                return True

        logger.info(f"Starting Docker service: {docker_name}")

        try:
            # Run docker compose up -d
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "up",
                "-d",
                docker_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_KITTY_ROOT),
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=60.0,
            )

            if proc.returncode != 0:
                logger.error(
                    f"Docker compose up failed for {docker_name}: "
                    f"rc={proc.returncode}, stderr={stderr.decode()}"
                )
                return False

            logger.info(f"Docker compose up completed for {docker_name}")

            # Wait for health if requested
            if wait_for_health and self._health_checker:
                return await self._wait_for_health(service)

            return True

        except asyncio.TimeoutError:
            logger.error(f"Timeout starting {docker_name}")
            return False
        except Exception as e:
            logger.exception(f"Error starting {docker_name}: {e}")
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
        timeout: float = 10.0,
    ) -> bool:
        """Stop a Docker Compose service.

        Args:
            service: The service to stop.
            timeout: Timeout for docker stop command.

        Returns:
            True if service stopped, False otherwise.
        """
        if service.service_type not in (ServiceType.DOCKER_SERVICE, ServiceType.DOCKER_INFRA):
            logger.error(f"Service {service.name} is not a Docker service")
            return False

        docker_name = service.docker_service_name or service.name

        logger.info(f"Stopping Docker service: {docker_name}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "stop",
                "-t",
                str(int(timeout)),
                docker_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_KITTY_ROOT),
            )

            await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout + 10,
            )

            if proc.returncode != 0:
                logger.warning(f"Docker compose stop returned non-zero for {docker_name}")

            return True

        except asyncio.TimeoutError:
            logger.error(f"Timeout stopping {docker_name}")
            return False
        except Exception as e:
            logger.exception(f"Error stopping {docker_name}: {e}")
            return False

    async def restart_service(
        self,
        service: ServiceDefinition,
        wait_for_health: bool = True,
    ) -> bool:
        """Restart a Docker Compose service.

        Args:
            service: The service to restart.
            wait_for_health: Whether to wait for health after restart.

        Returns:
            True if service restarted successfully.
        """
        docker_name = service.docker_service_name or service.name

        logger.info(f"Restarting Docker service: {docker_name}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "restart",
                docker_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_KITTY_ROOT),
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=60.0,
            )

            if proc.returncode != 0:
                logger.error(f"Docker compose restart failed for {docker_name}")
                return False

            if wait_for_health and self._health_checker:
                return await self._wait_for_health(service)

            return True

        except Exception as e:
            logger.exception(f"Error restarting {docker_name}: {e}")
            return False

    async def get_container_id(self, service: ServiceDefinition) -> Optional[str]:
        """Get the container ID for a service.

        Args:
            service: The service to get container ID for.

        Returns:
            Container ID if running, None otherwise.
        """
        docker_name = service.docker_service_name or service.name

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "ps",
                "-q",
                docker_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_KITTY_ROOT),
            )

            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=10.0,
            )

            container_id = stdout.decode().strip()
            return container_id if container_id else None

        except Exception:
            return None

    async def is_running(self, service: ServiceDefinition) -> bool:
        """Check if a Docker service container is running.

        Args:
            service: The service to check.

        Returns:
            True if container is running.
        """
        container_id = await self.get_container_id(service)
        if not container_id:
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=10.0,
            )

            return stdout.decode().strip().lower() == "true"

        except Exception:
            return False

    async def get_container_info(self, service: ServiceDefinition) -> Optional[Dict]:
        """Get container info for a service.

        Args:
            service: The service to get info for.

        Returns:
            Container info dict or None.
        """
        container_id = await self.get_container_id(service)
        if not container_id:
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "inspect",
                container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=10.0,
            )

            data = json.loads(stdout.decode())
            return data[0] if data else None

        except Exception:
            return None
