"""
ProcessManager: Python subprocess control for llama.cpp servers.

Provides programmatic start/stop/restart of local LLM servers,
replacing manual bash script invocation with integrated Python control.

Works alongside IdleReaper for automatic memory management on Mac Studio.
"""

import asyncio
import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .types import ModelTier
from .registry import ENDPOINTS, ModelEndpoint

logger = logging.getLogger("brain.parallel.process_manager")


@dataclass
class ServerConfig:
    """Configuration for starting a llama.cpp server."""
    model_path: str
    port: int
    alias: str
    context_size: int
    n_parallel: int
    batch_size: int = 512
    threads: int = 8
    n_gpu_layers: int = 999
    mmproj_path: Optional[str] = None  # For vision models
    flash_attn: bool = True
    jinja: bool = True
    extra_args: Optional[Dict[str, str]] = None


# Default server configurations derived from ops/scripts/llama/start.sh
def _get_server_configs() -> Dict[ModelTier, ServerConfig]:
    """Build server configurations from environment variables."""
    model_base = os.getenv("MODEL_BASE", "/Users/Shared/Coding/models")

    return {
        ModelTier.Q4_TOOLS: ServerConfig(
            model_path=os.path.join(
                model_base,
                os.getenv("LLAMACPP_Q4_MODEL", "athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf")
            ),
            port=int(os.getenv("LLAMACPP_Q4_PORT", "8083")),
            alias=os.getenv("LLAMACPP_Q4_ALIAS", "kitty-q4"),
            context_size=int(os.getenv("LLAMACPP_Q4_CTX", "131072")),
            n_parallel=int(os.getenv("LLAMACPP_Q4_PARALLEL", "6")),
            batch_size=512,
            threads=8,
            extra_args={
                "--rope-scaling": "yarn",
                "--yarn-orig-ctx": "32768",
                "--yarn-ext-factor": "4.0",
                "--override-kv": "llama.context_length=int:131072",
                "-kvu": "",
            },
        ),
        ModelTier.VISION: ServerConfig(
            model_path=os.path.join(
                model_base,
                os.getenv("LLAMACPP_VISION_MODEL", "gemma-3-27b-it-GGUF/gemma-3-27b-it-q4_k_m.gguf")
            ),
            mmproj_path=os.path.join(
                model_base,
                os.getenv("LLAMACPP_VISION_MMPROJ", "gemma3_27b_mmproj/mmproj-model-f16.gguf")
            ),
            port=int(os.getenv("LLAMACPP_VISION_PORT", "8086")),
            alias=os.getenv("LLAMACPP_VISION_ALIAS", "kitty-vision"),
            context_size=int(os.getenv("LLAMACPP_VISION_CTX", "8192")),
            n_parallel=int(os.getenv("LLAMACPP_VISION_PARALLEL", "2")),
            batch_size=int(os.getenv("LLAMACPP_VISION_BATCH_SIZE", "1024")),
            threads=int(os.getenv("LLAMACPP_VISION_THREADS", "12")),
            jinja=False,  # Vision model doesn't use jinja
        ),
        ModelTier.CODER: ServerConfig(
            model_path=os.path.join(
                model_base,
                os.getenv("LLAMACPP_CODER_MODEL", "Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q8_0.gguf")
            ),
            port=int(os.getenv("LLAMACPP_CODER_PORT", "8087")),
            alias=os.getenv("LLAMACPP_CODER_ALIAS", "kitty-coder"),
            context_size=int(os.getenv("LLAMACPP_CODER_CTX", "32768")),
            n_parallel=int(os.getenv("LLAMACPP_CODER_PARALLEL", "4")),
            batch_size=2048,
            threads=8,
        ),
        ModelTier.SUMMARY: ServerConfig(
            model_path=os.path.join(
                model_base,
                os.getenv("LLAMACPP_SUMMARY_MODEL", "Hermes-3-8B/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf")
            ),
            port=int(os.getenv("LLAMACPP_SUMMARY_PORT", "8084")),
            alias=os.getenv("LLAMACPP_SUMMARY_ALIAS", "kitty-summary"),
            context_size=4096,
            n_parallel=4,
            batch_size=512,
            threads=4,
            jinja=False,
        ),
    }


class ProcessManager:
    """
    Manages llama.cpp server processes for local LLM inference.

    Provides:
    - Start/stop/restart of llama.cpp servers by tier
    - PID tracking and health monitoring
    - Integration with IdleReaper for auto-shutdown
    - Graceful shutdown with timeout fallback to SIGKILL

    Usage:
        manager = ProcessManager()

        # Start a server
        pid = await manager.start_server(ModelTier.Q4_TOOLS)

        # Check if running
        if manager.is_running(ModelTier.Q4_TOOLS):
            print("Server is up")

        # Stop gracefully
        await manager.stop_server(ModelTier.Q4_TOOLS)
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        server_configs: Optional[Dict[ModelTier, ServerConfig]] = None,
    ):
        """
        Initialize the process manager.

        Args:
            log_dir: Directory for server logs (defaults to .logs/)
            server_configs: Custom server configurations (uses defaults if None)
        """
        project_root = Path(__file__).parents[5]  # services/brain/src/brain/agents/parallel -> root
        self._log_dir = Path(log_dir) if log_dir else project_root / ".logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._server_configs = server_configs or _get_server_configs()
        self._processes: Dict[ModelTier, subprocess.Popen] = {}
        self._lock = asyncio.Lock()

    def _build_command(self, config: ServerConfig) -> list:
        """Build the llama-server command line arguments."""
        cmd = [
            "llama-server",
            "--model", config.model_path,
            "--host", "0.0.0.0",
            "--port", str(config.port),
            "--n-gpu-layers", str(config.n_gpu_layers),
            "--ctx-size", str(config.context_size),
            "-np", str(config.n_parallel),
            "--batch-size", str(config.batch_size),
            "--threads", str(config.threads),
            "--alias", config.alias,
        ]

        if config.mmproj_path:
            cmd.extend(["--mmproj", config.mmproj_path])

        if config.flash_attn:
            cmd.extend(["--flash-attn", "on"])

        if config.jinja:
            cmd.append("--jinja")

        if config.extra_args:
            for key, value in config.extra_args.items():
                if value:
                    cmd.extend([key, value])
                else:
                    cmd.append(key)

        return cmd

    def _check_port_in_use(self, port: int) -> bool:
        """Check if a port is already in use."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    async def start_server(self, tier: ModelTier) -> Optional[int]:
        """
        Start a llama.cpp server for the specified tier.

        Args:
            tier: Model tier to start

        Returns:
            PID of the started process, or None if failed/already running
        """
        async with self._lock:
            config = self._server_configs.get(tier)
            if not config:
                logger.error(f"No configuration for tier {tier.value}")
                return None

            # Check if already running (either tracked or via port)
            if tier in self._processes:
                proc = self._processes[tier]
                if proc.poll() is None:
                    logger.warning(f"Server for {tier.value} already running (PID {proc.pid})")
                    return proc.pid

            if self._check_port_in_use(config.port):
                logger.warning(f"Port {config.port} already in use for {tier.value}")
                return None

            # Build and start the server
            cmd = self._build_command(config)
            log_file = self._log_dir / f"llamacpp-{tier.value.replace('_', '-')}.log"

            logger.info(f"Starting {tier.value} server on port {config.port}")
            logger.debug(f"Command: {' '.join(cmd)}")

            try:
                with open(log_file, "a") as log:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        preexec_fn=os.setsid,  # New process group for clean shutdown
                    )

                self._processes[tier] = proc

                # Write PID file for compatibility with bash scripts
                pid_file = self._log_dir / f"llamacpp-{tier.value.replace('_', '-')}.pid"
                pid_file.write_text(str(proc.pid))

                # Update endpoint running state
                endpoint = ENDPOINTS.get(tier)
                if endpoint:
                    endpoint._is_running = True

                logger.info(f"Started {tier.value} server (PID {proc.pid})")
                return proc.pid

            except Exception as e:
                logger.error(f"Failed to start {tier.value} server: {e}")
                return None

    async def stop_server(self, tier: ModelTier, graceful_timeout: float = 5.0) -> bool:
        """
        Stop a llama.cpp server for the specified tier.

        Args:
            tier: Model tier to stop
            graceful_timeout: Seconds to wait for graceful shutdown before SIGKILL

        Returns:
            True if server was stopped, False if not running or failed
        """
        async with self._lock:
            proc = self._processes.get(tier)
            if not proc:
                logger.warning(f"No tracked process for {tier.value}")
                return False

            if proc.poll() is not None:
                logger.debug(f"Server {tier.value} already terminated")
                del self._processes[tier]
                return True

            logger.info(f"Stopping {tier.value} server (PID {proc.pid})")

            try:
                # Try graceful shutdown first (SIGTERM to process group)
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

                # Wait for graceful shutdown
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, proc.wait),
                        timeout=graceful_timeout,
                    )
                    logger.info(f"Server {tier.value} stopped gracefully")
                except asyncio.TimeoutError:
                    # Force kill if graceful shutdown didn't work
                    logger.warning(f"Graceful shutdown timeout, force killing {tier.value}")
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait()

                del self._processes[tier]

                # Update endpoint running state
                endpoint = ENDPOINTS.get(tier)
                if endpoint:
                    endpoint._is_running = False

                # Remove PID file
                pid_file = self._log_dir / f"llamacpp-{tier.value.replace('_', '-')}.pid"
                if pid_file.exists():
                    pid_file.unlink()

                return True

            except ProcessLookupError:
                logger.debug(f"Process {tier.value} already gone")
                del self._processes[tier]
                return True
            except Exception as e:
                logger.error(f"Error stopping {tier.value}: {e}")
                return False

    async def restart_server(self, tier: ModelTier) -> Optional[int]:
        """
        Restart a llama.cpp server for the specified tier.

        Args:
            tier: Model tier to restart

        Returns:
            PID of the new process, or None if failed
        """
        await self.stop_server(tier)
        # Brief delay to ensure port is freed
        await asyncio.sleep(0.5)
        return await self.start_server(tier)

    def is_running(self, tier: ModelTier) -> bool:
        """
        Check if a server is running for the specified tier.

        Args:
            tier: Model tier to check

        Returns:
            True if server is running, False otherwise
        """
        proc = self._processes.get(tier)
        if proc and proc.poll() is None:
            return True

        # Also check port as fallback (server might have been started externally)
        config = self._server_configs.get(tier)
        if config:
            return self._check_port_in_use(config.port)

        return False

    def get_status(self) -> Dict[str, Dict]:
        """
        Get status of all servers.

        Returns:
            Dict mapping tier name to status dict
        """
        result = {}
        for tier, config in self._server_configs.items():
            proc = self._processes.get(tier)
            result[tier.value] = {
                "running": self.is_running(tier),
                "pid": proc.pid if proc and proc.poll() is None else None,
                "port": config.port,
                "alias": config.alias,
            }
        return result

    async def stop_all(self) -> None:
        """Stop all running servers."""
        for tier in list(self._processes.keys()):
            await self.stop_server(tier)

    async def start_all(self) -> Dict[ModelTier, Optional[int]]:
        """
        Start all configured servers.

        Returns:
            Dict mapping tier to PID (or None if failed)
        """
        results = {}
        for tier in self._server_configs:
            results[tier] = await self.start_server(tier)
        return results


# Singleton instance
_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get or create the global process manager instance."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager


async def reset_process_manager() -> None:
    """Reset the global process manager (for testing)."""
    global _process_manager
    if _process_manager:
        await _process_manager.stop_all()
    _process_manager = None
