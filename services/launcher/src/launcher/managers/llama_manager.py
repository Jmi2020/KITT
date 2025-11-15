"""llama.cpp server management and monitoring."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import httpx


@dataclass
class LlamaServerStatus:
    """Status of llama.cpp server."""

    running: bool
    url: str
    model: Optional[str] = None
    n_ctx: Optional[int] = None
    n_gpu_layers: Optional[int] = None
    error: Optional[str] = None


DEFAULT_PORT = 8080
LEGACY_PORTS = (8082, 8081)
PID_FILE = Path(".logs/llamacpp.pid")


@dataclass
class LlamaServerConfig:
    """Configuration for a llama.cpp server instance."""

    label: str
    port: int
    alias: str
    enabled: bool = True


@dataclass
class LlamaInstanceStatus(LlamaServerStatus):
    """Status + metadata for a specific llama.cpp instance."""

    name: str = "llama.cpp"
    port: int = 0
    enabled: bool = True


class LlamaManager:
    """Manage llama.cpp server monitoring with automatic port discovery."""

    def __init__(
        self,
        host: str = "localhost",
        port: Optional[int] = None,
        timeout: float = 2.0,
    ):
        """Initialize llama.cpp manager.

        Args:
            host: Server hostname
            port: Server port (defaults to LLAMACPP_PORT env var or 8082)
            timeout: HTTP request timeout in seconds
        """
        self.host = host
        self.timeout = timeout
        self._configured_port = port or self._read_configured_port()
        self._discovered_port: Optional[int] = None

    @property
    def base_url(self) -> str:
        """Return the best-known llama.cpp base URL."""
        port = self._discovered_port or self._configured_port
        return f"http://{self.host}:{port}"

    def _read_configured_port(self) -> int:
        env_port = os.getenv("LLAMACPP_PORT")
        if env_port and env_port.isdigit():
            return int(env_port)
        return DEFAULT_PORT

    async def get_status(self) -> LlamaServerStatus:
        """Get llama.cpp server status.

        Returns:
            LlamaServerStatus with health and model info
        """
        statuses = await self.get_all_statuses()
        for status in statuses:
            if status.enabled:
                return status
        return statuses[0] if statuses else LlamaServerStatus(
            running=False,
            url=f"http://{self.host}:{self._configured_port}",
            error="No servers configured",
        )

    async def get_all_statuses(self) -> list[LlamaInstanceStatus]:
        """Get status for all configured llama.cpp servers."""
        configs = self._server_configs()
        process_ports = self._ports_from_processes()
        statuses: list[LlamaInstanceStatus] = []
        seen_ports: set[int] = set()

        for config in configs:
            seen_ports.add(config.port)
            url = f"http://{self.host}:{config.port}"

            if not config.enabled:
                statuses.append(
                    LlamaInstanceStatus(
                        running=False,
                        url=url,
                        model=None,
                        n_ctx=None,
                        n_gpu_layers=None,
                        error="Disabled via env",
                        name=config.label,
                        port=config.port,
                        enabled=False,
                    )
                )
                continue

            status = await self._probe_port(config.port)
            if status.running:
                self._discovered_port = config.port

            proc_alias = process_ports.get(config.port, {}).get("alias")
            statuses.append(
                LlamaInstanceStatus(
                    running=status.running,
                    url=status.url,
                    model=status.model,
                    n_ctx=status.n_ctx,
                    n_gpu_layers=status.n_gpu_layers,
                    error=status.error,
                    name=proc_alias or config.label or config.alias or f"Port {config.port}",
                    port=config.port,
                    enabled=True,
                )
            )

        # Include any extra candidate ports we haven't checked yet (e.g., legacy, PID hints)
        for port in self._candidate_ports():
            if port in seen_ports:
                continue
            seen_ports.add(port)
            status = await self._probe_port(port)
            if not status.running:
                continue
            proc_alias = process_ports.get(port, {}).get("alias")
            statuses.append(
                LlamaInstanceStatus(
                    running=True,
                    url=status.url,
                    model=status.model,
                    n_ctx=status.n_ctx,
                    n_gpu_layers=status.n_gpu_layers,
                    error=None,
                    name=proc_alias or f"Server on {port}",
                    port=port,
                    enabled=True,
                )
            )

        return statuses

    async def _probe_port(self, port: int) -> LlamaServerStatus:
        base_url = f"http://{self.host}:{port}"
        url = f"{base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    model_info = await self._get_model_info(client, base_url)
                    return LlamaServerStatus(
                        running=True,
                        url=base_url,
                        model=model_info.get("model"),
                        n_ctx=model_info.get("n_ctx"),
                        n_gpu_layers=model_info.get("n_gpu_layers"),
                    )
                return LlamaServerStatus(
                    running=False,
                    url=base_url,
                    error=f"Server returned {response.status_code}",
                )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return LlamaServerStatus(
                running=False,
                url=base_url,
                error=f"Connection failed: {type(e).__name__}",
            )
        except Exception as e:
            return LlamaServerStatus(
                running=False,
                url=base_url,
                error=f"Error: {e}",
            )

    async def _get_model_info(self, client: httpx.AsyncClient, base_url: str) -> dict:
        """Get model information from server.

        Args:
            client: HTTP client to use

        Returns:
            Dictionary with model info or empty dict on error
        """
        try:
            # Try to get model info from /props endpoint
            response = await client.get(f"{base_url}/props")
            if response.status_code == 200:
                data = response.json()
                return {
                    "model": data.get("default_generation_settings", {}).get(
                        "model", "unknown"
                    ),
                    "n_ctx": data.get("default_generation_settings", {}).get("n_ctx"),
                    "n_gpu_layers": data.get("default_generation_settings", {}).get(
                        "n_gpu_layers"
                    ),
                }
        except Exception:
            pass

        return {}

    def _candidate_ports(self) -> Iterable[int]:
        """Generate ports to probe: configured, running processes, pid hint, legacy."""
        seen = set()

        def add(port: Optional[int]):
            if port and port not in seen:
                seen.add(port)
                yield port

        yield from add(self._configured_port)
        yield from add(self._discovered_port)
        for proc_port in self._ports_from_processes().keys():
            yield from add(proc_port)
        yield from add(self._port_from_pid())
        for legacy in LEGACY_PORTS:
            yield from add(legacy)

    def _ports_from_processes(self) -> dict[int, dict]:
        """Discover ports/aliases from running llama-server processes."""
        try:
            import psutil
        except ImportError:
            return {}

        ports: dict[int, dict] = {}
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                name = proc.info.get("name", "") or ""
                cmdline = proc.info.get("cmdline") or []
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            if "llama-server" not in name and not any("llama-server" in part for part in cmdline):
                continue

            port = None
            alias = None
            for idx, token in enumerate(cmdline):
                if token == "--port" and idx + 1 < len(cmdline):
                    try:
                        port = int(cmdline[idx + 1])
                    except ValueError:
                        continue
                elif token.startswith("--port="):
                    try:
                        port = int(token.split("=", 1)[1])
                    except ValueError:
                        continue
                elif token == "--alias" and idx + 1 < len(cmdline):
                    alias = cmdline[idx + 1]
                elif token.startswith("--alias="):
                    alias = token.split("=", 1)[1]

            if port:
                ports[port] = {"alias": alias}

        return ports

    def _server_configs(self) -> list[LlamaServerConfig]:
        """Build server config list from environment overrides."""

        def env_int(name: str, default: int) -> int:
            value = os.getenv(name)
            if value and value.isdigit():
                return int(value)
            return default

        def env_bool(name: str, default: bool = True) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().lower() not in {"0", "false", "off", "no"}

        configs: list[LlamaServerConfig] = [
            LlamaServerConfig(
                label=os.getenv("LLAMACPP_Q4_ALIAS", "Athene (Q4)"),
                port=env_int("LLAMACPP_Q4_PORT", 8083),
                alias=os.getenv("LLAMACPP_Q4_ALIAS", "kitty-q4"),
                enabled=env_bool("LLAMACPP_Q4_ENABLED", True),
            ),
            LlamaServerConfig(
                label=os.getenv("LLAMACPP_F16_ALIAS", "Llama (F16)"),
                port=env_int("LLAMACPP_F16_PORT", 8082),
                alias=os.getenv("LLAMACPP_F16_ALIAS", "kitty-f16"),
                enabled=env_bool("LLAMACPP_F16_ENABLED", True),
            ),
            LlamaServerConfig(
                label=os.getenv("LLAMACPP_SUMMARY_ALIAS", "Hermes Summary"),
                port=env_int("LLAMACPP_SUMMARY_PORT", 8084),
                alias=os.getenv("LLAMACPP_SUMMARY_ALIAS", "kitty-summary"),
                enabled=env_bool("LLAMACPP_SUMMARY_ENABLED", True),
            ),
            LlamaServerConfig(
                label=os.getenv("LLAMACPP_VISION_ALIAS", "Gemma Vision"),
                port=env_int("LLAMACPP_VISION_PORT", 8085),
                alias=os.getenv("LLAMACPP_VISION_ALIAS", "kitty-vision"),
                enabled=env_bool("LLAMACPP_VISION_ENABLED", True),
            ),
        ]

        return configs

    def _port_from_pid(self) -> Optional[int]:
        """Try to read the running port from the llama.cpp process."""
        pid = None
        try:
            if PID_FILE.exists():
                pid = int(PID_FILE.read_text().strip())
        except Exception:
            pid = None

        if not pid:
            return None

        try:
            import psutil

            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline())
            match = re.search(r"--port\s+(\d+)", cmdline)
            if match:
                return int(match.group(1))
        except Exception:
            return None

        return None

    def get_process_status(self) -> bool:
        """Check if llama.cpp process is running via process list.

        Returns:
            True if llama-server or llama-cpp-python process found
        """
        try:
            import psutil

            for proc in psutil.process_iter(["name", "cmdline"]):
                try:
                    name = proc.info["name"]
                    cmdline = " ".join(proc.info["cmdline"] or [])

                    if "llama-server" in name or "llama-server" in cmdline:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return False
        except ImportError:
            # psutil not available - fall back to HTTP check only
            return False
