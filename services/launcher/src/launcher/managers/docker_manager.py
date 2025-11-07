"""Docker service management using docker-py."""

from dataclasses import dataclass
from typing import Optional

import docker
from docker.errors import DockerException


@dataclass
class ServiceStatus:
    """Status of a Docker service."""

    name: str
    state: str  # running, exited, created, etc.
    health: str  # healthy, unhealthy, starting, none
    ports: dict
    image: str
    created: str


class DockerManager:
    """Manage Docker Compose services."""

    def __init__(self, compose_file: str = "infra/compose/docker-compose.yml"):
        """Initialize Docker manager.

        Args:
            compose_file: Path to docker-compose.yml relative to project root
        """
        self.compose_file = compose_file
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        """Get or create Docker client."""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def is_docker_running(self) -> bool:
        """Check if Docker daemon is running."""
        try:
            self.client.ping()
            return True
        except DockerException:
            return False

    def list_services(self, project_name: str = "compose") -> list[ServiceStatus]:
        """List all Docker Compose services.

        Args:
            project_name: Docker Compose project name (default: compose)

        Returns:
            List of ServiceStatus objects
        """
        if not self.is_docker_running():
            return []

        services = []
        try:
            # Filter containers by compose project label
            containers = self.client.containers.list(
                all=True, filters={"label": f"com.docker.compose.project={project_name}"}
            )

            for container in containers:
                # Get service name from labels
                service_name = container.labels.get("com.docker.compose.service", container.name)

                # Get health status
                health_status = "none"
                if container.attrs.get("State", {}).get("Health"):
                    health_status = container.attrs["State"]["Health"]["Status"]

                # Get port mappings
                ports = {}
                port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {})
                for container_port, host_bindings in port_bindings.items():
                    if host_bindings:
                        ports[container_port] = host_bindings[0].get("HostPort", "")

                services.append(
                    ServiceStatus(
                        name=service_name,
                        state=container.status,
                        health=health_status,
                        ports=ports,
                        image=container.image.tags[0] if container.image.tags else "unknown",
                        created=container.attrs.get("Created", ""),
                    )
                )

        except DockerException as e:
            # Return empty list on error
            return []

        return sorted(services, key=lambda s: s.name)

    def get_service_logs(
        self, service_name: str, tail: int = 100, project_name: str = "compose"
    ) -> str:
        """Get logs from a service.

        Args:
            service_name: Name of the service
            tail: Number of lines to tail
            project_name: Docker Compose project name

        Returns:
            Log output as string
        """
        try:
            containers = self.client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"com.docker.compose.project={project_name}",
                        f"com.docker.compose.service={service_name}",
                    ]
                },
            )

            if not containers:
                return f"No container found for service: {service_name}"

            container = containers[0]
            logs = container.logs(tail=tail, timestamps=True).decode("utf-8")
            return logs

        except DockerException as e:
            return f"Error getting logs: {e}"

    def restart_service(self, service_name: str, project_name: str = "compose") -> bool:
        """Restart a specific service.

        Args:
            service_name: Name of the service to restart
            project_name: Docker Compose project name

        Returns:
            True if successful, False otherwise
        """
        try:
            containers = self.client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"com.docker.compose.project={project_name}",
                        f"com.docker.compose.service={service_name}",
                    ]
                },
            )

            if not containers:
                return False

            container = containers[0]
            container.restart()
            return True

        except DockerException:
            return False

    def stop_service(self, service_name: str, project_name: str = "compose") -> bool:
        """Stop a specific service.

        Args:
            service_name: Name of the service to stop
            project_name: Docker Compose project name

        Returns:
            True if successful, False otherwise
        """
        try:
            containers = self.client.containers.list(
                filters={
                    "label": [
                        f"com.docker.compose.project={project_name}",
                        f"com.docker.compose.service={service_name}",
                    ]
                },
            )

            if not containers:
                return False

            container = containers[0]
            container.stop()
            return True

        except DockerException:
            return False

    def start_service(self, service_name: str, project_name: str = "compose") -> bool:
        """Start a specific service.

        Args:
            service_name: Name of the service to start
            project_name: Docker Compose project name

        Returns:
            True if successful, False otherwise
        """
        try:
            containers = self.client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"com.docker.compose.project={project_name}",
                        f"com.docker.compose.service={service_name}",
                    ]
                },
            )

            if not containers:
                return False

            container = containers[0]
            container.start()
            return True

        except DockerException:
            return False
