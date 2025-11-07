"""llama.cpp server management and monitoring."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

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
        for port in self._candidate_ports():
            status = await self._probe_port(port)
            if status.running:
                self._discovered_port = port
                return status

        # Use last status if any probes were attempted; otherwise, return generic failure.
        return status if "status" in locals() else LlamaServerStatus(
            running=False,
            url=f"http://{self.host}:{self._configured_port}",
            error="Unable to connect to llama.cpp on any known port",
        )

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
        """Generate ports to probe: configured, discovered, pid hint, legacy."""
        seen = set()

        def add(port: Optional[int]):
            if port and port not in seen:
                seen.add(port)
                yield port

        yield from add(self._configured_port)
        yield from add(self._discovered_port)
        yield from add(self._port_from_pid())
        for legacy in LEGACY_PORTS:
            yield from add(legacy)

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
