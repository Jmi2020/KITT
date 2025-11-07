"""llama.cpp server management and monitoring."""

import os
from dataclasses import dataclass
from typing import Optional

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


class LlamaManager:
    """Manage llama.cpp server monitoring."""

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
        self.port = port or int(os.getenv("LLAMACPP_PORT", "8082"))
        self.timeout = timeout
        self.base_url = f"http://{self.host}:{self.port}"

    async def get_status(self) -> LlamaServerStatus:
        """Get llama.cpp server status.

        Returns:
            LlamaServerStatus with health and model info
        """
        url = f"{self.base_url}/health"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    # Server is healthy - try to get model info
                    model_info = await self._get_model_info(client)

                    return LlamaServerStatus(
                        running=True,
                        url=self.base_url,
                        model=model_info.get("model"),
                        n_ctx=model_info.get("n_ctx"),
                        n_gpu_layers=model_info.get("n_gpu_layers"),
                    )
                else:
                    return LlamaServerStatus(
                        running=False,
                        url=self.base_url,
                        error=f"Server returned {response.status_code}",
                    )

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return LlamaServerStatus(
                running=False,
                url=self.base_url,
                error=f"Connection failed: {type(e).__name__}",
            )
        except Exception as e:
            return LlamaServerStatus(
                running=False,
                url=self.base_url,
                error=f"Error: {e}",
            )

    async def _get_model_info(self, client: httpx.AsyncClient) -> dict:
        """Get model information from server.

        Args:
            client: HTTP client to use

        Returns:
            Dictionary with model info or empty dict on error
        """
        try:
            # Try to get model info from /props endpoint
            response = await client.get(f"{self.base_url}/props")
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
